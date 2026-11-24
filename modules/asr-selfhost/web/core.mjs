const join = (left, right) => left + (left && right && /[a-z0-9]$/i.test(left) && /^[a-z0-9]/i.test(right) ? " " : "") + right;

export function createDraft(initial = "") {
  let version = 0, base = initial, text = initial, latest = "", manual = false, pending = "", done = false, anchor = "";
  const view = () => ({ text, latest, manual, pending, appendable: manual && latest.startsWith(anchor), done, version });
  return {
    view,
    begin() {
      ++version;
      base = text;
      latest = "";
      manual = false;
      anchor = "";
      done = false;
      // A rejected or unapplied suggestion belongs to the previous take.
      pending = "";
      return version;
    },
    edit(value) { if (!manual) anchor = latest; text = value; manual = true; return view(); },
    receive(token, { confirmed = "", draft = "", done: final = false } = {}) {
      if (version !== token || done) return view();
      latest = confirmed + draft;
      done = final;
      if (!manual) text = join(base, latest);
      else pending = latest.startsWith(anchor) ? latest.slice(anchor.length) : latest;
      return view();
    },
    appendSuggestion() {
      if (pending && latest.startsWith(anchor)) { text = join(text, pending); pending = ""; anchor = latest; }
      return view();
    },
    invalidate() { version++; done = true; return view(); },
  };
}
