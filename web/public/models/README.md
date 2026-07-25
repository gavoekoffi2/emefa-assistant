# Bundled face model

`emefa-canonical-face.obj` is the MediaPipe canonical face model (468 landmarks), sourced from:

https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/modules/face_geometry/data/canonical_face_model.obj

MediaPipe is licensed under the Apache License 2.0:

https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE

The model is bundled locally so EMEFA's realtime face rendering does not depend on a third-party network request.

## How it is used

`src/face/canonicalFace.ts` parses this file directly rather than using three's
`OBJLoader`. The loader returns a non-indexed geometry, which discards the
canonical landmark numbering that the whole facial rig addresses features by
(eyelid contours, lip rings, brow arcs, the face oval). Parsing in-house keeps
vertex *n* addressable as landmark *n*.

The eye and inner-mouth triangle patches are removed on load so the sockets and
the mouth are real apertures. Replacing this model with a different topology
will fail `web/tests/face.test.js`, which asserts the landmark indices land on
the anatomy they are named for.
