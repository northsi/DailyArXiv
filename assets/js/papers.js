(() => {
  "use strict";
  const list = document.getElementById("paper-list");
  if (!list) return;
  const cards = Array.from(list.querySelectorAll(".paper-card"));
  const search = document.getElementById("paper-search");
  const topic = document.getElementById("topic-filter");
  const sort = document.getElementById("paper-sort");
  const newOnly = document.getElementById("new-only");
  const count = document.getElementById("result-count");
  const empty = document.getElementById("no-results");
  const records = cards.map((card, index) => ({
    card,
    index,
    text: card.textContent.toLocaleLowerCase(),
  }));

  function update() {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    const ordered = [...records];
    if (sort.value !== "digest") {
      ordered.sort((a, b) => {
        const comparison = a.card.dataset.date.localeCompare(
          b.card.dataset.date,
        );
        return (
          (sort.value === "newest" ? -comparison : comparison) ||
          a.index - b.index
        );
      });
    }
    for (const { card, text } of ordered) {
      const matches =
        (!query || text.includes(query)) &&
        (!topic.value || card.dataset.topic === topic.value) &&
        (!newOnly.checked || card.dataset.new === "true");
      card.hidden = !matches;
      if (matches) visible += 1;
      list.appendChild(card);
    }
    count.textContent = `${visible} of ${cards.length} papers`;
    empty.hidden = visible !== 0 || cards.length === 0;
  }

  search.addEventListener("input", update);
  [topic, sort, newOnly].forEach((control) =>
    control.addEventListener("change", update),
  );
  document.getElementById("reset-filters").addEventListener("click", () => {
    search.value = "";
    topic.value = "";
    sort.value = "digest";
    newOnly.checked = false;
    update();
    search.focus();
  });
  document.getElementById("paper-filters").hidden = false;
  update();
})();
