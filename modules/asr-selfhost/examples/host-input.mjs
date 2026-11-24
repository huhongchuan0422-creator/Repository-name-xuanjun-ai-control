import {createAsrClient} from "../web/sdk.mjs";
import {createDraft} from "../web/core.mjs";

/** Host injects its own textarea and configured ASR mount URL. Call start() only
 * on a user action. Start the host microphone in onReady, pass PCM into the
 * returned pushPCM, and call stop after flushing the microphone's last bytes. */
export function bindVoiceInput({textarea, baseUrl, hotwords=[], onReady, onResult, onError}) {
  const client = createAsrClient({baseUrl});
  const draft = createDraft(textarea.value);
  let session, version;
  const edit = () => draft.edit(textarea.value);
  const render = () => {
    const view = draft.view();
    if (!view.manual) textarea.value = view.text;
    return view;
  };
  textarea.addEventListener("input",edit);
  return {
    status: client.status,
    start() {
      if (session && session.state !== "closed") return false;
      version = draft.begin();
      session = client.open({
        hotwords,onReady,onError,
        onResult(event) { draft.receive(version,event); onResult?.(event,render()); },
      });
      return true;
    },
    pushPCM(pcm) { return session?.pushPCM(pcm) ?? false; },
    stop() { return session?.stop() ?? false; },
    destroy() { session?.cancel(); draft.invalidate(); textarea.removeEventListener("input",edit); },
  };
}
