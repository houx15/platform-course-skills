# Platform HTML interaction contract

## Delivery

- Deliver one self-contained HTML5 file.
- Embed CSS and JavaScript.
- Do not load external scripts, stylesheets, images, audio, video, iframes, or fonts.
- Use UTF-8.

## Canvas

- Fill the iframe surface with a fluid layout: normally `width: 100%`, `min-height: 100%`, responsive grid/flex tracks, and vertical overflow when content is taller.
- Declare `aspectRatio: "1:1"`, `"4:3"`, or `"fill"` on the CourseDefinition Block as a design hint. Do not use that hint to clamp the HTML document itself.
- Do not centre and transform a fixed design box from `transform-origin: top left`, resize `body` to the scaled footprint, or use a fixed `aspect-ratio` wrapper together with `overflow: hidden`.
- Prevent horizontal scrolling.
- Keep essential content, feedback, unmet-requirement guidance, and the completion control reachable at 1280×720 and 1200×520.
- When the Block uses `openAs: "modal"`, inspect both the launcher inside the Slice and the opened dialog. Keep primary teaching context inline; the modal may hold the large interaction when the launcher remains understandable.

## Completion

- Label the visible button `完成` or `完成任务`.
- Do not emit completion before the confirmed condition is met.
- A blocking activity completes only after the platform receives a valid completion message.

## Typography

- Declare a verifiable `font-size` of at least `16px` on `html` or `body`.
- Learner content and controls (`button`, `input`, `select`, `textarea`) remain at least `16px`, including responsive states.
- Only text explicitly marked `.auxiliary` or `[data-text-role="auxiliary"]` may use `14px`; no visible text may be below `14px`.
- Use px, resolvable rem, `inherit`, or `clamp()` whose minimum is a safe px/rem value. Values such as em, %, vw, vh, or `calc()` cannot be proven by the static checker and block upload.

## Message

```javascript
const PROTOCOL = "mind-course-interaction";
const VERSION = "1.0";
let sessionToken = null;
const pendingFrameMessages = [];
let completionSent = false;

function postFrameMessage(type, payload) {
  window.parent.postMessage({
    protocol: PROTOCOL,
    version: VERSION,
    sessionToken,
    type,
    payload
  }, "*");
}

function send(type, payload) {
  if (!sessionToken) {
    pendingFrameMessages.push({ type, payload });
    return;
  }
  postFrameMessage(type, payload);
}

window.addEventListener("message", (event) => {
  const message = event.data;
  if (message.protocol !== PROTOCOL ||
      message.version !== VERSION ||
      !message.sessionToken) return;
  const isNewSession = sessionToken !== message.sessionToken;
  sessionToken = message.sessionToken;
  if (!isNewSession) return;
  postFrameMessage("ready", {});
  while (pendingFrameMessages.length) {
    const pending = pendingFrameMessages.shift();
    postFrameMessage(pending.type, pending.payload);
  }
});

function completeInteraction() {
  if (completionSent) return;
  completionSent = true;
  send("completed", {
    resultId: "stable-attempt-id",
    value: {
      answer: "option-id",
      attempts: 1
    },
    correct: true
  });
}

// Call completeInteraction() only from the activity's real completion exit.
```

The frame may send `ready`, `progress`, `completed`, or `error`. Every message echoes the current host-issued token. Messages created before the handshake are queued and flushed only after `ready`; a silent `if (!sessionToken) return` loses valid student actions and is rejected. A completed payload must contain `correct` and/or JSON-compatible `value` learning evidence. `resultId` is an optional stable identity for duplicate completion detection. The host always stamps the Block ID as `interactionId`; the frame must not invent or rely on that identity. Include `correct` only for objectively graded interactions. The authoring validator checks these fields, but browser/runtime persistence remains a separate platform verification.

## Repairing an existing interaction

Protocol repair changes the message adapter, not the activity. Preserve DOM/CSS, learner copy, answers, scoring, feedback, state transitions, completion thresholds, and blocking behavior. Remove legacy `INTERACTION_COMPLETE` only after every original completion exit reaches the new `completed` message. Keep the teacher's source untouched, repair a delivery copy, and always retain or reuse a SHA-named rollback copy under `.course-work/html-backups/`, including the first imported delivery copy.

Do not use `fetch`, XMLHttpRequest, WebSocket, EventSource, beacon APIs, browser storage, cookies, opener/top access, or `parent.document`. The file is self-contained and communicates only through the message protocol.

## Validation

Run `scripts/validate-html.py HTML_FILE --course-definition-2`. Existing `.course-work/html-reports/` files remain schemaVersion 1.1 artifacts until replaced by the 2.0 course-level validation report; do not use a legacy passing report as G6 evidence.

Treat the report as a static contract check, not a browser screenshot or real iframe test. It always records `browserCheckRequired: true`.
