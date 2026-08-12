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
window.parent.postMessage({
  type: "INTERACTION_COMPLETE",
  version: "1.0",
  payload: {
    lessonId: "stable-lesson-id",
    duration: 120,
    interactions: [
      {
        interactionId: "stable-interaction-id",
        type: "choice",
        answer: "option-id",
        correctAnswer: "option-id",
        isCorrect: true,
        duration: 15
      }
    ]
  }
}, "*");
```

Every interaction requires `interactionId`, `type`, and `answer`. Include correctness fields only for objectively graded interactions.

## Validation

Run the toolkit HTML validator, then generate deterministic JSON and Markdown under `.course-work/html-reports/`. Regenerate both after every HTML change; a missing or stale report blocks full Review.

Treat the report as a static contract check, not a browser screenshot or real iframe test. It always records `browserCheckRequired: true`.
