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
  acquireHubAccessTokenDetailed,
  clearMailboxProfileCache,
  forceRetryOfficeSso,
  getCachedMailboxEmail,
  getMailboxProfileId,
  getOfficeUserEmail,
  setMailboxProfileId,
  type SsoErrorInfo,
} from "./api/auth";
import {
  analyzeMessage,
  confirmOutbound,
  connectMailbox,
  fetchHealth,
  fetchMailboxProfile,
  inspectMailboxProfile,
  submitFeedback,
  syncMailboxIndex,
  type HistoryProfileStatus,
  type ProfileInspect,
} from "./api/client";
import { mapSuggestion } from "./api/mappers";
import { AnalyzingState } from "./components/AnalyzingState";
import { CheckProfilePanel } from "./components/CheckProfilePanel";
import { ConfirmOutboundDialog } from "./components/ConfirmOutboundDialog";
import { HubUnavailable } from "./components/HubUnavailable";
import { RoutePicker } from "./components/RoutePicker";
import { SignInPanel } from "./components/SignInPanel";
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
  profileOk: { color: "#2F5D50", marginTop: "8px" },
  profileBusy: { color: "#5B6B73", marginTop: "8px" },
});

function historyProfileLabel(
  status: HistoryProfileStatus,
  err: string | null,
  signedIn: boolean
): string {
  if (!signedIn) {
    return "Sign in to build or refresh the mailbox profile.";
  }
  if (status === "syncing" || status === "not_started") {
    return "Profiel opbouwen… (analyze kan gewoon door)";
  }
  if (status === "failed") {
    return err
      ? `Profiel bijwerken mislukt: ${err}`
      : "Profiel bijwerken mislukt — eerdere geschiedenis blijft bruikbaar.";
  }
  return "Mailbox-profiel klaar";
}

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
  const [historyStatus, setHistoryStatus] = useState<HistoryProfileStatus>("not_started");
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [needsSignIn, setNeedsSignIn] = useState(false);
  const [ssoError, setSsoError] = useState<SsoErrorInfo | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileInspect, setProfileInspect] = useState<ProfileInspect | null>(null);
  const analyzeSeq = useRef(0);
  const inspectSeq = useRef(0);
  const historyPollRef = useRef<number | null>(null);
  /** One history refresh per taskpane session per mailbox profile. */
  const historyRefreshedFor = useRef<string | null>(null);
  /** Prevent re-analyze when pane state flips (analyzing → ready would otherwise loop). */
  const didInitialAnalyze = useRef(false);

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
    const attempt = async (): Promise<boolean> => {
      const health = await fetchHealth();
      return health.status === "ok";
    };
    try {
      let ok = false;
      try {
        ok = await attempt();
      } catch {
        // One quick retry — Studio LAN / Docker publish is occasionally slow to answer.
        await new Promise((r) => window.setTimeout(r, 800));
        ok = await attempt();
      }
      if (!ok) {
        setState("unavailable");
        setUnavailableMessage("Hub reported an unhealthy status.");
        clearSuggestion();
        return;
      }
      setState("idle");
    } catch {
      setState("unavailable");
      setUnavailableMessage(
        "The SpoqSense hub cannot be reached on the LAN (Mac Studio :8000 via webpack proxy). Check the Studio is awake and Retry."
      );
      clearSuggestion();
    } finally {
      setRetrying(false);
    }
  }, [clearSuggestion]);

  const stopHistoryPoll = useCallback(() => {
    if (historyPollRef.current != null) {
      window.clearInterval(historyPollRef.current);
      historyPollRef.current = null;
    }
  }, []);

  const refreshHistoryProfile = useCallback(
    (token: string, profileId: string) => {
      // Fire-and-forget: do not block analyze. Hub runs ≤300 bootstrap / incremental sync.
      setHistoryStatus("syncing");
      setHistoryError(null);
      void syncMailboxIndex({
        token,
        mailboxProfileId: profileId,
        maxMessages: 300,
        wait: false,
      })
        .then((result) => {
          setHistoryStatus(result.history_status);
          setHistoryError(result.history_sync_error);
          if (result.history_status === "syncing") {
            stopHistoryPoll();
            historyPollRef.current = window.setInterval(() => {
              void fetchMailboxProfile({ token, mailboxProfileId: profileId })
                .then((snap) => {
                  setHistoryStatus(snap.history_status);
                  setHistoryError(snap.history_sync_error);
                  if (snap.history_status === "ready" || snap.history_status === "failed") {
                    stopHistoryPoll();
                  }
                })
                .catch(() => {
                  /* keep last known status */
                });
            }, 4000);
          }
        })
        .catch((err: unknown) => {
          setHistoryStatus("failed");
          setHistoryError(err instanceof Error ? err.message : "Sync failed");
        });
    },
    [stopHistoryPoll]
  );

  const connectMailboxSession = useCallback(
    async (
      token: string,
      connectEmail: string,
      kind: "personal" | "shared"
    ): Promise<string | null> => {
      try {
        const connected = await connectMailbox({
          token,
          email: connectEmail,
          kind,
        });
        setMailboxProfileId(connected.id, connectEmail);
        return connected.id;
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : "Mailbox connect failed");
        return null;
      }
    },
    []
  );

  const ensureSession = useCallback(async (): Promise<{
    token: string;
    profileId: string;
  } | null> => {
    const acquired = await acquireHubAccessTokenDetailed();
    if (!acquired.ok) {
      setNeedsSignIn(true);
      setSsoError(acquired.ssoError);
      setErrorMessage(null);
      return null;
    }
    setNeedsSignIn(false);
    setSsoError(null);
    const token = acquired.token;

    const mail = await getSelectedMail();
    const sharedEmail = getSharedMailboxEmail()?.toLowerCase() || null;
    const officeEmail = getOfficeUserEmail()?.toLowerCase() || null;
    // Never use the selected message's From: as mailbox identity — that churns
    // profile cache when switching mails and feels like a new profile.
    const isShared = Boolean(mail?.isSharedContext && sharedEmail) || Boolean(sharedEmail);
    const connectEmail = (isShared ? sharedEmail : officeEmail) || null;
    if (!connectEmail) {
      setErrorMessage(
        isShared
          ? "Shared mailbox e-mail ontbreekt — kan geen stabiel profiel koppelen."
          : "Could not read mailbox identity from Outlook."
      );
      return null;
    }
    const kind: "personal" | "shared" = isShared ? "shared" : "personal";

    let profileId = getMailboxProfileId();
    const cachedEmail = getCachedMailboxEmail();
    if (profileId && cachedEmail && cachedEmail !== connectEmail) {
      clearMailboxProfileCache();
      profileId = null;
    }

    if (!profileId) {
      profileId = await connectMailboxSession(token, connectEmail, kind);
      if (!profileId) return null;
    }

    // Outlook open / first session touch only — not on every analyze.
    if (historyRefreshedFor.current !== profileId) {
      historyRefreshedFor.current = profileId;
      refreshHistoryProfile(token, profileId);
    }
    return { token, profileId };
  }, [connectMailboxSession, refreshHistoryProfile]);

  const loadProfileInspect = useCallback(
    async (includeSummary = true) => {
      const seq = ++inspectSeq.current;
      setProfileLoading(true);
      setProfileError(null);
      try {
        let session = await ensureSession();
        if (!session) {
          if (seq !== inspectSeq.current) return;
          setProfileInspect(null);
          setProfileError("Sign in / connect first to view the mailbox profile.");
          return;
        }
        try {
          const data = await inspectMailboxProfile({
            token: session.token,
            mailboxProfileId: session.profileId,
            includeSummary,
          });
          if (seq !== inspectSeq.current) return;
          setProfileInspect(data);
        } catch (err) {
          const status = (err as Error & { status?: number }).status;
          if (status === 401) {
            if (seq !== inspectSeq.current) return;
            setNeedsSignIn(true);
            setProfileError("Sessie verlopen — meld opnieuw aan.");
            return;
          }
          if (status === 404) {
            clearMailboxProfileCache();
            historyRefreshedFor.current = null;
            session = await ensureSession();
            if (!session) {
              if (seq !== inspectSeq.current) return;
              setProfileInspect(null);
              setProfileError("Profiel niet gevonden — reconnect mislukt.");
              return;
            }
            const data = await inspectMailboxProfile({
              token: session.token,
              mailboxProfileId: session.profileId,
              includeSummary,
            });
            if (seq !== inspectSeq.current) return;
            setProfileInspect(data);
            return;
          }
          throw err;
        }
      } catch (err) {
        if (seq !== inspectSeq.current) return;
        setProfileError(err instanceof Error ? err.message : "Profiel laden mislukt");
      } finally {
        if (seq === inspectSeq.current) setProfileLoading(false);
      }
    },
    [ensureSession]
  );

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
      const msg = err instanceof Error ? err.message : "Analyze failed";
      if (/401|unauthor|auth/i.test(msg)) {
        setNeedsSignIn(true);
        setSsoError({
          code: "hub_401",
          message: "Hub rejected the access token. Retry SSO or paste a fresh token.",
        });
        setState("idle");
        setErrorMessage(null);
        return;
      }
      setState("error");
      setErrorMessage(msg);
    }
  }, [clearSuggestion, ensureSession]);

  useEffect(() => {
    void checkHub();
  }, [checkHub]);

  useEffect(() => {
    return () => stopHistoryPoll();
  }, [stopHistoryPoll]);

  useEffect(() => {
    if (state === "unavailable" || state === "checking") return;
    // One-shot bootstrap when hub becomes available — do NOT depend on later
    // pane states (ready_*/analyzing) or every completed analyze restarts.
    if (!didInitialAnalyze.current) {
      didInitialAnalyze.current = true;
      void ensureSession().then((session) => {
        if (session) void runAnalyze();
      });
    }
    return onMailSelectionChanged(() => {
      void runAnalyze();
    });
  }, [state, runAnalyze, ensureSession]);

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
        <Spinner label="Checking SpoqSense hub…" />
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
      <Title3>SpoqSense</Title3>

      <Text
        className={
          historyStatus === "ready"
            ? styles.profileOk
            : historyStatus === "failed"
              ? styles.warn
              : styles.profileBusy
        }
        block
        aria-live="polite"
      >
        {historyProfileLabel(historyStatus, historyError, !needsSignIn)}
      </Text>

      {needsSignIn ? (
        <SignInPanel
          ssoError={ssoError}
          onRetrySso={() => {
            void forceRetryOfficeSso().then((result) => {
              if (result.ok) {
                setNeedsSignIn(false);
                setSsoError(null);
                void ensureSession().then((session) => {
                  if (session) void runAnalyze();
                });
                return;
              }
              setNeedsSignIn(true);
              setSsoError(result.ssoError);
            });
          }}
          onTokenReady={() => {
            setNeedsSignIn(false);
            setSsoError(null);
            void ensureSession().then((session) => {
              if (session) void runAnalyze();
            });
          }}
        />
      ) : null}

      {!needsSignIn && state === "idle" && !suggestion ? (
        <Text className={styles.meta} block>
          Select a message in Outlook to analyze. No suggestion is shown until analysis completes.
        </Text>
      ) : null}

      {state === "analyzing" ? <AnalyzingState /> : null}

      {!needsSignIn && (state === "error" || errorMessage) ? (
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
          onGenerateResponse={() => void runAnalyze()}
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
          onGenerateResponse={() => void runAnalyze()}
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

      {!needsSignIn ? (
        <Button
          appearance="secondary"
          style={{ marginTop: 8 }}
          onClick={() => {
            setProfileOpen(true);
            void loadProfileInspect(true);
          }}
        >
          Check profiel
        </Button>
      ) : null}

      {profileOpen ? (
        <CheckProfilePanel
          data={profileInspect}
          loading={profileLoading}
          error={profileError}
          onClose={() => {
            setProfileOpen(false);
            setProfileError(null);
          }}
          onRetrySummary={() => void loadProfileInspect(true)}
        />
      ) : null}

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
