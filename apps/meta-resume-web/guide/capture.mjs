/** Browser camera and transient previews. No upload, storage or model endpoint. */
const MAX_IMAGE_BYTES = 2_000_000;

function problem(code, message) { return Object.assign(new Error(message), { code }); }
export async function imageDigest(bytes) {
  if (!globalThis.crypto?.subtle) throw problem('INSECURE_CONTEXT', 'Open this page on HTTPS or localhost to use photos.');
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, '0')).join('');
}

export function createCaptureController({ video, onState = () => {}, now = Date.now }) {
  let stream = null, epoch = 0, sequence = 0, expiryTimer = null, disposed = false;
  let activeRequest = null;
  const announce = (state, message) => onState({ state, message });
  function stop(message = 'Camera stopped.') {
    epoch += 1;
    clearTimeout(expiryTimer); expiryTimer = null;
    const previous = stream; stream = null; activeRequest = null;
    previous?.getTracks().forEach((track) => track.stop());
    video.pause(); video.srcObject = null;
    announce('idle', message);
  }
  async function start({ userGesture = false, requestId, expiresAtMs }) {
    if (disposed) throw problem('DISPOSED', 'This camera view has closed.');
    if (!userGesture || document.hidden || navigator.userActivation?.isActive === false) {
      throw problem('VISIBLE_ACTION_REQUIRED', 'Use the visible camera button while this page is open.');
    }
    if (!globalThis.isSecureContext) throw problem('INSECURE_CONTEXT', 'Camera access needs HTTPS or localhost. A selected photo can still be previewed.');
    if (typeof navigator.mediaDevices?.getUserMedia !== 'function') throw problem('NO_MEDIA', 'This browser has no camera access. You can preview a selected photo instead.');
    if (!requestId || !Number.isFinite(expiresAtMs) || expiresAtMs <= now()) throw problem('REQUEST_EXPIRED', 'This photo request expired. Ask for a new view.');
    stop('Opening camera…');
    const generation = epoch;
    activeRequest = { requestId, expiresAtMs };
    expiryTimer = setTimeout(() => stop('Photo request expired. Camera stopped.'), Math.max(0, expiresAtMs - now()));
    announce('requesting', 'Waiting for your browser’s camera permission…');
    let acquired;
    try {
      acquired = await navigator.mediaDevices.getUserMedia({ audio: false, video: {
        facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 960 },
      } });
      if (disposed || generation !== epoch || document.hidden || now() >= expiresAtMs) {
        acquired.getTracks().forEach((track) => track.stop());
        throw problem('CAPTURE_CANCELLED', 'Camera request cancelled. No frame was kept.');
      }
      stream = acquired; video.srcObject = stream;
      await video.play();
      if (generation !== epoch || document.hidden) throw problem('CAPTURE_CANCELLED', 'Camera request cancelled.');
      for (const track of stream.getVideoTracks()) track.addEventListener('ended', () => {
        if (generation === epoch) stop('Camera connection ended. Try opening it again.');
      }, { once: true });
      announce('live', 'Live browser camera. Take one photo when you are ready.');
    } catch (error) {
      acquired?.getTracks().forEach((track) => track.stop());
      if (generation === epoch) stop('Camera is off.');
      if (error.code) throw error;
      if (error.name === 'NotAllowedError' || error.name === 'SecurityError') throw problem('CAMERA_DENIED', 'Camera permission was not granted. You can change it in your browser or preview a photo.');
      if (error.name === 'NotFoundError' || error.name === 'OverconstrainedError') throw problem('NO_CAMERA', 'No suitable camera is available. You can preview a photo instead.');
      if (error.name === 'NotReadableError') throw problem('CAMERA_BUSY', 'The camera may be in use by another app. Close that app and try again.');
      throw problem('CAMERA_ERROR', 'The camera could not open. Your confirmed items are unchanged.');
    }
  }
  async function takePhoto() {
    const generation = epoch, request = activeRequest;
    if (!stream || !request || document.hidden || now() >= request.expiresAtMs) throw problem('NO_LIVE_FRAME', 'Open a new camera view before taking a photo.');
    if (!video.videoWidth || !video.videoHeight || video.readyState < 2) throw problem('FRAME_NOT_READY', 'The camera is still starting. Wait for the preview, then try again.');
    const scale = Math.min(1, 1280 / video.videoWidth, 1280 / video.videoHeight);
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
    canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
    const capturedAtMs = now();
    canvas.getContext('2d', { alpha: false }).drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', .86));
    canvas.width = 0; canvas.height = 0;
    if (!blob || blob.size > MAX_IMAGE_BYTES) throw problem('IMAGE_LIMIT', 'That photo is too large. Try a simpler close-up.');
    const bytes = new Uint8Array(await blob.arrayBuffer()), sha256 = await imageDigest(bytes);
    if (generation !== epoch || document.hidden || now() >= request.expiresAtMs) throw problem('CAPTURE_CANCELLED', 'This photo request ended before the frame was ready. No frame was kept.');
    sequence += 1;
    stop('Photo taken. Camera is off.');
    return { bytes, sha256, mimeType: 'image/jpeg', capturedAtMs, sequence, source: 'phone-camera', blob };
  }
  const onVisibility = () => { if (document.hidden) stop('Page hidden. Camera stopped.'); };
  const onPageHide = () => stop('Page closed. Camera stopped.');
  document.addEventListener('visibilitychange', onVisibility);
  window.addEventListener('pagehide', onPageHide);
  return { start, takePhoto, stop, get live() { return Boolean(stream); },
    dispose() { disposed = true; stop(); document.removeEventListener('visibilitychange', onVisibility); window.removeEventListener('pagehide', onPageHide); },
  };
}

export async function readSelectedImage(file) {
  if (!(file instanceof Blob) || !['image/png', 'image/jpeg'].includes(file.type) || !file.size || file.size > MAX_IMAGE_BYTES) {
    throw problem('IMAGE_LIMIT', 'Choose one PNG or JPEG photo up to 2 MB. It stays in this page.');
  }
  const bytes = new Uint8Array(await file.arrayBuffer());
  const png = bytes.length >= 8 && [137, 80, 78, 71, 13, 10, 26, 10].every((value, i) => bytes[i] === value);
  const jpeg = bytes.length >= 3 && bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255;
  if ((file.type === 'image/png' && !png) || (file.type === 'image/jpeg' && !jpeg)) throw problem('IMAGE_FORMAT', 'The selected file does not match its PNG or JPEG type.');
  return { bytes, sha256: globalThis.crypto?.subtle ? await imageDigest(bytes) : null, mimeType: file.type,
    capturedAtMs: 0, sequence: 0, source: 'selected-image', blob: file };
}

export async function createDemoImage() {
  const canvas = document.createElement('canvas'); canvas.width = 960; canvas.height = 640;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#303b2e'; ctx.fillRect(0, 0, 960, 640);
  ctx.fillStyle = '#59674c'; ctx.fillRect(70, 190, 820, 360);
  ctx.fillStyle = '#d8ccb1'; ctx.fillRect(130, 250, 230, 250);
  ctx.fillStyle = '#7d8aaf'; ctx.fillRect(150, 230, 230, 250);
  ctx.fillStyle = '#eff0e2'; ctx.beginPath(); ctx.roundRect(525, 280, 155, 155, 26); ctx.fill();
  ctx.strokeStyle = '#e4e8d4'; ctx.lineWidth = 12; ctx.beginPath(); ctx.moveTo(585, 281); ctx.lineTo(585, 245); ctx.moveTo(625, 281); ctx.lineTo(625, 245); ctx.stroke();
  ctx.fillStyle = '#172116'; ctx.fillRect(575, 410, 55, 9);
  ctx.fillStyle = '#e5ead8'; ctx.font = '600 24px system-ui'; ctx.fillText('A charger on the workbench', 70, 105);
  ctx.fillStyle = '#bfccae'; ctx.font = '18px system-ui'; ctx.fillText('ILLUSTRATED SAMPLE · NOT A CAMERA CAPTURE', 70, 145);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
  canvas.width = 0; canvas.height = 0;
  const bytes = new Uint8Array(await blob.arrayBuffer());
  return { bytes, sha256: globalThis.crypto?.subtle ? await imageDigest(bytes) : null, mimeType: 'image/png',
    capturedAtMs: 0, sequence: 0, source: 'demo', blob };
}
