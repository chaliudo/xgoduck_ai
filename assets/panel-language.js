/* Chinese-only panels: labels come from each element's data-zh value or the zh argument. */
(() => {
  const t = (en, zh) => zh;
  const labels = new Map();
  for (const element of document.querySelectorAll('[data-zh]')) {
    labels.set(element, () => element.dataset.zh);
  }
  const attributes = ['alt', 'aria-label', 'title'].flatMap(attr =>
    [...document.querySelectorAll(`[data-zh-${attr}]`)].map(element =>
      [element, attr, element.getAttribute('data-zh-' + attr)]));

  function renderLabel(element, label) {
    const value = label();
    if (element.textContent !== value) element.textContent = value;
  }

  function setText(id, label) {
    const element = document.getElementById(id);
    if (!element) return;
    labels.set(element, label);
    renderLabel(element, label);
  }

  function render() {
    document.documentElement.lang = 'zh-CN';
    for (const [element, label] of labels) renderLabel(element, label);
    for (const [element, attr, zh] of attributes) {
      if (zh === null) element.removeAttribute(attr);
      else element.setAttribute(attr, zh);
    }
  }

  window.DuckPanelLanguage = { t, setText, get chinese() { return true; } };
  render();
})();
