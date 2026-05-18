// hooks/useVideoCapture.ts
export function useVideoCapture() {
  const startRecording = async (canvas: HTMLCanvasElement) => {
    const stream = canvas.captureStream(60);
    const recorder = new MediaRecorder(stream, {
      mimeType: "video/webm;codecs=vp9",
      videoBitsPerSecond: 50000000,
    });
    const chunks: Blob[] = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.start();
    return {
      stop: () => new Promise<Blob>((resolve) => {
        recorder.onstop = () => resolve(new Blob(chunks, { type: "video/webm" }));
        recorder.stop();
      }),
    };
  };
  return { startRecording };
}
