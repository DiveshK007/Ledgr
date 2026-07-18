import { useRef, useState } from "react";

// The "ledger line" ask box. Supports attaching photos (for Supplier quote
// slips / Collections ledger pages) via a plain file input styled as a
// text link, and a mic button for voice queries (MediaRecorder -> webm
// blob -> onAskVoice), since "through conversational AI" is the literal
// track requirement and typing isn't really that.

export default function Console({ onAsk, onAskVoice, loading }) {
  const [query, setQuery] = useState("");
  const [files, setFiles] = useState([]);
  const [recording, setRecording] = useState(false);
  const fileInputRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  function handleSubmit(e) {
    e.preventDefault();
    if (!query.trim() || loading) return;
    onAsk(query.trim(), files);
  }

  async function toggleRecording() {
    if (loading) return;

    if (recording) {
      mediaRecorderRef.current?.stop();
      setRecording(false);
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      alert("Microphone access isn't available in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        stream.getTracks().forEach((t) => t.stop());
        onAskVoice(blob);
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch (err) {
      alert("Couldn't access the microphone: " + err.message);
    }
  }

  return (
    <form className="entry-line" onSubmit={handleSubmit}>
      <span className="no">Entry &mdash;</span>
      <input
        type="text"
        placeholder="who should I follow up with for payment this week"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        disabled={loading}
      />
      <label className="file-label">
        {files.length > 0 ? `${files.length} photo(s)` : "attach photos"}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(e) => setFiles(Array.from(e.target.files || []))}
        />
      </label>
      <button
        type="button"
        onClick={toggleRecording}
        disabled={loading}
        style={recording ? { background: "#a3392f" } : undefined}
        title={recording ? "Stop recording" : "Ask by voice"}
      >
        {recording ? "Stop" : "Speak"}
      </button>
      <button type="submit" disabled={loading}>
        {loading ? "Thinking..." : "Ask"}
      </button>
    </form>
  );
}
