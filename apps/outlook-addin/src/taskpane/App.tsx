import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Button,
  makeStyles,
  Spinner,
  Text,
  Textarea,
  Title3,
} from "@fluentui/react-components";
import {
  acquireHubAccessToken,
  clearMailboxProfileCache,
  getCachedMailboxEmail,
  getMailboxProfileId,
  getOfficeUserEmail,
  setMailboxProfileId,
} from "./api/auth";
import {
  analyzeMessage,
  confirmOutbound,
  connectMailbox,
  fetchHealth,
  submitFeedback,
  syncMailboxIndex,
} from "./api/client";
import { mapSuggestion } from "./api/mappers";
import { AnalyzingState } from "./components/AnalyzingState";
import { ConfirmOutboundDialog } from "./components/ConfirmOutboundDialog";
import { HubUnavailable } from "./components/HubUnavailable";
import { RoutePicker } from "./components/RoutePicker";
import { SuggestionHero } from "./components/SuggestionHero";
import { SuggestionReviewStack } from "./components/SuggestionReviewStack";
import {
  getSelectedMail,
  getSharedMailboxEmail,
  onMailSelectionChanged,
} from "./office/officeMail";
import type { PaneState, SuggestionViewModel } from "./state/paneState";

const useStyles = makeStyles({
  root: {
    padding: "16px",
    minHeight: "100vh",
    boxSizing: "border-box",
    backgroundColor: "#F3F7FA",
  },
  meta: { marginTop: "12px", color: "#5B6B73" },
  center: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    padding: "16px",
    minHeight: "100vh",
    boxSizing: "border-box",
    backgroundColor: "#F3F7FA",
  },
  warn: { color: "#8A4B08", marginTop: "8px" },
});

function newIdempotencyKey(): string {
  return `idem-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function App(): React.JSX.Element {
  const styles = useStyles();
  const [state, setState] = useState<PaneState>("checking");
  const [suggestion, setSuggestion] = useState<SuggestionViewModel | null>(null);
  const [unavailableMessage, setUnavailableMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [editDraft, setEditDraft] = useState("");
  const [pickingRoute, setPickingRoute] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [pendingAction, setPendingAction] = useState<"send" | "forward">("send");
  const [recipients, setRecipients] = useState<string[]>([]);
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const analyzeSeq = useRef(0);

  const clearSuggestion = useCallback(() => {
    setSuggestion(null);
    setErrorMessage(null);
    setPickingRoute(false);
    setConfirmOpen(false);
    setIdempotencyKey(null);
  }, []);

  const checkHub = useCallback(async () => {
    setRetrying(true);
    setUnavailableMessage(null);
    try {
      const health = await fetchHealth();
      if (health.status !== "ok") {
        setState("unavailable");
        setUnavailableMessage("Hub reported an unhealthy status.");
        clearSuggestion();
        return;
      }
      setState("idle");
    } catch {
      setState("unavailable");
      setUnavailableMessage(
        "The SpoqAssist hub cannot be reached. Check Tailscale/VPN and try again."
      );
      clearSuggestion();
    } finally {
      setRetrying(false);
    }
  }, [clearSuggestion]);

  const ensureSession = useCallback(async (): Promise<{
    token: string;
    profileId: string;
  } | null> => {
    const token = await acquireHubAccessToken();
    if (!token) {
      setErrorMessage(
        "Sign-in required. Configure Office SSO (see docs/runbooks/office-sso-setup.md) or set localStorage spoq_access_token for sideload."
      );
      return null;
    }

    const mail = await getSelectedMail();
    const sharedEmail = getSharedMailboxEmail();
    const isShared = Boolean(mail?.isSharedContext || sharedEmail);
    const connectEmail = (
      isShared ? sharedEmail || mail?.sender : getOfficeUserEmail()
    )?.toLowerCase();
    if (!connectEmail) {
      setErrorMessage("Could not read mailbox identity from Outlook.");
      return null;
    }

    let profileId = getMailboxProfileId();
    const cachedEmail = getCachedMailboxEmail();
    if (profileId && cachedEmail && cachedEmail !== connectEmail) {
      clearMailboxProfileCache();
      profileId = null;
    }

    if (!profileId) {
      try {
        const connected = await connectMailbox({
          token,
          email: connectEmail,
          kind: isShared ? "shared" : "personal",
        });
        profileId = connected.id;
        setMailboxProfileId(profileId, connectEmail);
        // Initial Sent Items crawl for grounded drafts (hub also auto-syncs if empty).
        try {
          await syncMailboxIndex({
            token,
            mailboxProfileId: profileId,
            maxMessages: 100,
          });
        } catch {
          /* analyze path will retry ensure_history_indexed */
        }
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : "Mailbox connect failed");
        return null;
      }
    }
    return { token, profileId };
  }, []);

  const runAnalyze = useCallback(async () => {
    const seq = ++analyzeSeq.current;
    const session = await ensureSession();
    if (!session) {
      setState("idle");
      return;
    }
    const mail = await getSelectedMail();
    if (!mail) {
      setState("idle");
      clearSuggestion();
      return;
    }
    setState("analyzing");
    clearSuggestion();
    try {
      const api = await analyzeMessage({
        token: session.token,
        mailboxProfileId: session.profileId,
        messageId: mail.itemId,
        subject: mail.subject,
        body: mail.body,
        sender: mail.sender,
        attachmentNames: mail.attachmentNames,
      });
      if (seq !== analyzeSeq.current) return;
      const vm = mapSuggestion(api);
      setSuggestion(vm);
      setEditDraft(vm.draft || "");
      setState(vm.confidence === "high" ? "ready_hero" : "ready_review");
    } catch (err) {
      if (seq !== analyzeSeq.current) return;
      setSuggestion(null);
      setState("error");
      setErrorMessage(err instanceof Error ? err.message : "Analyze failed");
    }
  }, [clearSuggestion, ensureSession]);

  useEffect(() => {
    void checkHub();
  }, [checkHub]);

  useEffect(() => {
    if (state === "unavailable" || state === "checking") return;
    return onMailSelectionChanged(() => {
      void runAnalyze();
    });
  }, [state, runAnalyze]);

  const onAccept = () => {
    if (!suggestion) return;
    const action = suggestion.suggestedRoute ? "forward" : "send";
    if (action === "send" && !suggestion.suggestedRoute) {
      // Require an explicit recipient — never use a placeholder.
      const fromDraft = window.prompt("Enter recipient email for send:");
      if (!fromDraft || !fromDraft.includes("@")) {
        setErrorMessage("A valid recipient email is required before confirm.");
        return;
      }
      setRecipients([fromDraft.trim()]);
    } else if (suggestion.suggestedRoute) {
      setRecipients([suggestion.suggestedRoute.email]);
    } else {
      setErrorMessage("No route or recipient available.");
      return;
    }
    setPendingAction(action);
    setIdempotencyKey((prev) => prev || newIdempotencyKey());
    setConfirmOpen(true);
    setState("confirming");
  };

  const onReject = async () => {
    if (!suggestion) return;
    try {
      const session = await ensureSession();
      if (session) {
        await submitFeedback({
          token: session.token,
          mailboxProfileId: session.profileId,
          suggestionId: suggestion.suggestionId,
          outcome: "reject",
        });
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Reject failed");
    }
    clearSuggestion();
    setState("idle");
  };

  const onConfirm = async () => {
    if (!suggestion) return;
    const session = await ensureSession();
    if (!session) return;
    const key = idempotencyKey || newIdempotencyKey();
    setIdempotencyKey(key);
    setConfirmBusy(true);
    try {
      await submitFeedback({
        token: session.token,
        mailboxProfileId: session.profileId,
        suggestionId: suggestion.suggestionId,
        outcome: "accept",
        editedDraft: editDraft,
      });
      await confirmOutbound({
        token: session.token,
        mailboxProfileId: session.profileId,
        suggestionId: suggestion.suggestionId,
        idempotencyKey: key,
        action: pendingAction,
        recipients,
        body: editDraft,
        aiAssisted: true,
      });
      setConfirmOpen(false);
      clearSuggestion();
      setState("idle");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Confirm failed");
    } finally {
      setConfirmBusy(false);
    }
  };

  if (state === "checking") {
    return (
      <main className={styles.center} aria-busy="true">
        <Spinner label="Checking SpoqAssist hub…" />
      </main>
    );
  }

  if (state === "unavailable") {
    return (
      <HubUnavailable
        message={unavailableMessage || undefined}
        onRetry={() => {
          setState("checking");
          void checkHub();
        }}
        retrying={retrying}
      />
    );
  }

  return (
    <main className={styles.root}>
      <Title3>SpoqAssist</Title3>

      {state === "idle" && !suggestion ? (
        <Text className={styles.meta} block>
          Select a message in Outlook to analyze. No suggestion is shown until analysis completes.
        </Text>
      ) : null}

      {state === "analyzing" ? <AnalyzingState /> : null}

      {state === "error" || errorMessage ? (
        <Text className={styles.warn} block>
          {errorMessage || "Something went wrong."}
        </Text>
      ) : null}

      {suggestion && (state === "ready_hero" || state === "confirming") ? (
        <SuggestionHero
          suggestion={suggestion}
          onAccept={onAccept}
          onEdit={() => {
            setState("editing");
            setEditDraft(suggestion.draft || "");
          }}
          onReject={() => void onReject()}
          onChangeRoute={() => setPickingRoute(true)}
        />
      ) : null}

      {suggestion && state === "ready_review" ? (
        <SuggestionReviewStack
          suggestion={suggestion}
          onAccept={onAccept}
          onEdit={() => {
            setState("editing");
            setEditDraft(suggestion.draft || "");
          }}
          onReject={() => void onReject()}
          onChangeRoute={() => setPickingRoute(true)}
        />
      ) : null}

      {state === "editing" && suggestion ? (
        <section>
          <Text weight="semibold">Edit draft</Text>
          <Textarea
            value={editDraft}
            onChange={(_, d) => setEditDraft(d.value)}
            style={{ width: "100%", marginTop: 8 }}
            rows={8}
          />
          <Button
            appearance="primary"
            style={{ marginTop: 8, backgroundColor: "#135067" }}
            onClick={onAccept}
          >
            Continue to confirm
          </Button>
        </section>
      ) : null}

      {pickingRoute ? (
        <RoutePicker
          onCancel={() => setPickingRoute(false)}
          onSelect={(email, name, teach) => {
            if (suggestion) {
              void ensureSession().then((session) => {
                if (!session) return;
                void submitFeedback({
                  token: session.token,
                  mailboxProfileId: session.profileId,
                  suggestionId: suggestion.suggestionId,
                  outcome: "reroute",
                  correctedRouteEmail: email,
                  correctedRouteName: name,
                  teach,
                });
              });
              setSuggestion({
                ...suggestion,
                suggestedRoute: { email, displayName: name },
              });
            }
            setRecipients([email]);
            setPickingRoute(false);
          }}
        />
      ) : null}

      {suggestion?.attachmentWarnings?.length ? (
        <Text className={styles.warn} block>
          {suggestion.attachmentWarnings.map((w) => `${w.name}: ${w.reason}`).join(" · ")}
        </Text>
      ) : null}

      <Button appearance="secondary" style={{ marginTop: 12 }} onClick={() => void runAnalyze()}>
        Analyze selected message
      </Button>

      {confirmOpen ? (
        <ConfirmOutboundDialog
          action={pendingAction}
          recipients={recipients}
          draftExcerpt={editDraft || suggestion?.draft || ""}
          aiAssisted
          busy={confirmBusy}
          onCancel={() => {
            setConfirmOpen(false);
            setState(suggestion?.confidence === "high" ? "ready_hero" : "ready_review");
          }}
          onConfirm={() => void onConfirm()}
        />
      ) : null}
    </main>
  );
}
