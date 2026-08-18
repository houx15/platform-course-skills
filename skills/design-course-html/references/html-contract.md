# Platform HTML interaction contract

## Delivery

- Deliver one self-contained HTML5 file.
- Embed CSS and JavaScript.
- Do not load external scripts, stylesheets, images, audio, video, iframes, or fonts.
- Use UTF-8.

## Canvas

- Use `aspect-ratio: 1 / 1` or horizontal `aspect-ratio: 4 / 3`.
- Fit inside an iframe through whole-canvas scaling.
- Prevent horizontal scrolling.
- Keep essential content and the completion control visible.

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

function send(type, payload) {
  if (!sessionToken) return;
  window.parent.postMessage({
    protocol: PROTOCOL,
    version: VERSION,
    sessionToken,
    type,
    payload
  }, "*");
}

window.addEventListener("message", (event) => {
  const message = event.data;
  if (message.protocol !== PROTOCOL ||
      message.version !== VERSION ||
      !message.sessionToken) return;
  sessionToken = message.sessionToken;
  send("ready", {});
});

send("completed", {
  resultId: "stable-attempt-id",
  value: {
    answer: "option-id",
    attempts: 1
  },
  correct: true
});
```

The frame may send `ready`, `progress`, `completed`, or `error`. Every message echoes the current host-issued token. A completed payload must contain `correct` and/or JSON-compatible `value` learning evidence. `resultId` is an optional stable identity for duplicate completion detection. The host always stamps the Block ID as `interactionId`; the frame must not invent or rely on that identity. Include `correct` only for objectively graded interactions. The authoring validator checks these fields, but browser/runtime persistence remains a separate platform verification.

Do not use `fetch`, XMLHttpRequest, WebSocket, EventSource, beacon APIs, browser storage, cookies, opener/top access, or `parent.document`. The file is self-contained and communicates only through the message protocol.

## Validation

Run `scripts/validate-html.py HTML_FILE --course-definition-2`. Existing `.course-work/html-reports/` files remain schemaVersion 1.1 artifacts until replaced by the 2.0 course-level validation report; do not use a legacy passing report as G6 evidence.

Treat the report as a static contract check, not a browser screenshot or real iframe test. It always records `browserCheckRequired: true`.
