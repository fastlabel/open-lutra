// Recording config fields: the hidden textarea holds what the form sends; the modal edits a draft of it.
document.querySelectorAll("[data-config-field]").forEach((field) => {
  const select = field.querySelector("[data-config-select]");
  const value = field.querySelector("[data-config-value]");
  const dialog = field.querySelector("[data-config-dialog]");
  const draft = field.querySelector("[data-config-draft]");
  const state = field.querySelector("[data-config-state]");
  let loaded = value.value;
  let source = state.dataset.source;
  let previous = select.value;

  const showState = () => {
    const edited = value.value !== loaded;
    state.textContent = edited ? "Edited (applied changes will be sent)" : source;
    state.classList.toggle("color-fg-attention", edited);
    field.querySelectorAll("[data-config-name]").forEach((name) => (name.textContent = select.value));
  };
  // Leaving by clicking outside (or Esc) may be accidental, so ask before dropping edits; Cancel is deliberate.
  const leave = () => {
    if (draft.value === value.value || window.confirm("Discard your edits and close?")) dialog.close();
  };

  field.querySelector("[data-config-open]").addEventListener("click", () => {
    draft.value = value.value;
    dialog.showModal();
    draft.focus();
    draft.setSelectionRange(0, 0);
    draft.scrollTop = 0;
  });
  field.querySelector("[data-config-apply]").addEventListener("click", () => {
    value.value = draft.value;
    dialog.close();
    showState();
  });
  field.querySelector("[data-config-cancel]").addEventListener("click", () => dialog.close());
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    leave();
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) leave();
  });

  select.addEventListener("change", async () => {
    if (value.value !== loaded && !window.confirm("Discard applied edits and switch to another file?")) {
      select.value = previous;
      return;
    }
    const response = await fetch(`/configs/content?name=${encodeURIComponent(select.value)}`);
    if (!response.ok) {
      window.alert(`Could not load ${select.value}.`);
      select.value = previous;
      return;
    }
    value.value = loaded = await response.text();
    source = "From file";
    previous = select.value;
    showState();
  });
});
