/** Sole Office.js import site (architecture). */

export interface SelectedMail {
  itemId: string;
  subject: string;
  body: string;
  sender: string;
  attachmentNames: string[];
  isSharedContext: boolean;
}

let _handlerRegistered = false;
let _stableLocalId: string | null = null;

export function getSelectedMail(): Promise<SelectedMail | null> {
  return new Promise((resolve) => {
    const item = Office.context.mailbox?.item;
    if (!item) {
      resolve(null);
      return;
    }
    let itemId = item.itemId || "";
    if (!itemId) {
      if (!_stableLocalId) {
        _stableLocalId = `local-${crypto.randomUUID?.() || String(Date.now())}`;
      }
      itemId = _stableLocalId;
    } else {
      _stableLocalId = null;
      // Graph /me/messages/{id} requires a REST id; Office.js itemId is EWS-format.
      try {
        const mailbox = Office.context.mailbox;
        if (typeof mailbox.convertToRestId === "function") {
          itemId = mailbox.convertToRestId(
            itemId,
            Office.MailboxEnums.RestVersion.v2_0
          );
        }
      } catch {
        /* keep EWS id; hub may still fail closed on Graph */
      }
    }

    const subject = item.subject || "";
    const sender =
      item.from?.emailAddress ||
      (item as unknown as { sender?: { emailAddress?: string } }).sender?.emailAddress ||
      "";

    const attachmentNames = (item.attachments || []).map((a) => a.name || "attachment");
    const isSharedContext = detectSharedContext();

    item.body.getAsync(Office.CoercionType.Text, (result) => {
      const body = result.status === Office.AsyncResultStatus.Succeeded ? result.value || "" : "";
      resolve({ itemId, subject, body, sender, attachmentNames, isSharedContext });
    });
  });
}

function detectSharedContext(): boolean {
  try {
    const mailbox = Office.context.mailbox as unknown as {
      userProfile?: { emailAddress?: string };
      item?: { sharedProperties?: { targetMailbox?: string } };
    };
    const userEmail = (mailbox.userProfile?.emailAddress || "").toLowerCase();
    const target = (mailbox.item?.sharedProperties?.targetMailbox || "").toLowerCase();
    if (target && userEmail && target !== userEmail) return true;
    // Some hosts expose shared folder via restUrl / diagnostics — best-effort only.
    const rest = (Office.context.mailbox as unknown as { restUrl?: string }).restUrl || "";
    if (/\/users\//i.test(rest) && !/\/me\//i.test(rest)) return true;
  } catch {
    /* ignore */
  }
  return false;
}

export function onMailSelectionChanged(handler: () => void): () => void {
  if (_handlerRegistered) {
    // Replace behavior: store latest handler via wrapper on mailbox object.
    (Office.context.mailbox as unknown as { __spoqHandler?: () => void }).__spoqHandler = handler;
    return () => {
      const box = Office.context.mailbox as unknown as { __spoqHandler?: () => void };
      if (box.__spoqHandler === handler) box.__spoqHandler = undefined;
    };
  }
  try {
    const box = Office.context.mailbox as unknown as { __spoqHandler?: () => void };
    box.__spoqHandler = handler;
    Office.context.mailbox.addHandlerAsync(Office.EventType.ItemChanged, () => {
      box.__spoqHandler?.();
    });
    _handlerRegistered = true;
  } catch {
    // Host may not support ItemChanged.
  }
  return () => {
    const box = Office.context.mailbox as unknown as { __spoqHandler?: () => void };
    if (box.__spoqHandler === handler) box.__spoqHandler = undefined;
  };
}

export function getSharedMailboxEmail(): string | null {
  try {
    const target = (
      Office.context.mailbox.item as unknown as {
        sharedProperties?: { targetMailbox?: string };
      }
    )?.sharedProperties?.targetMailbox;
    return target || null;
  } catch {
    return null;
  }
}
