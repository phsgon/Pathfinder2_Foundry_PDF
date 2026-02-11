const sectionsSchema = [
  {
    key: "summary",
    label: "Resumo (pagina 1)",
    children: [
      { key: "summary_stats", label: "Vida/CA/Percepcao" },
      { key: "summary_attributes", label: "Atributos" },
      { key: "summary_defenses", label: "Defesas" },
      { key: "summary_skills", label: "Pericias" },
    ],
  },
  {
    key: "talents_equipment",
    label: "Talentos e Equipamentos",
    children: [
      { key: "talents", label: "Talentos" },
      { key: "equipment", label: "Equipamentos" },
      { key: "inventory_notes", label: "Anotacoes de Inventario" },
    ],
  },
  {
    key: "info",
    label: "Informacoes do Personagem",
    children: [
      { key: "info_details", label: "Detalhes" },
      { key: "info_physical", label: "Informacoes Fisicas" },
      { key: "info_origin", label: "Origem" },
      { key: "info_data", label: "Dados do Personagem" },
      { key: "info_resist", label: "Resistencias e Imunidades" },
      { key: "info_actions", label: "Acoes e Atividades" },
    ],
  },
  {
    key: "spells",
    label: "Magias",
    children: [
      { key: "spells_list", label: "Lista de Magias" },
      { key: "spells_resources", label: "Foco e Recursos" },
      { key: "spells_notes", label: "Anotacoes de Magias" },
    ],
  },
];

let selectedJson = null;
let config = { sections: {} };
let sectionOrder = sectionsSchema.map((section) => section.key);
let jsonListCache = [];

const jsonList = document.getElementById("jsonList");
const selectedJsonEl = document.getElementById("selectedJson");
const enableAllBtn = document.getElementById("enableAll");
const previewBtn = document.getElementById("preview");
const generateBtn = document.getElementById("generate");
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const sectionsContainer = document.getElementById("sections");
const toast = document.getElementById("toast");

function showToast(text, success = true) {
  toast.textContent = text;
  toast.style.background = success ? "#1f3f33" : "#8b1e1e";
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2000);
}

function getDefaultConfig() {
  const defaults = {};
  sectionsSchema.forEach((section) => {
    defaults[section.key] = true;
    section.children.forEach((child) => {
      defaults[child.key] = true;
    });
  });
  return defaults;
}

function renderSections() {
  sectionsContainer.innerHTML = "";
  sectionOrder.forEach((sectionKey) => {
    const section = sectionsSchema.find((s) => s.key === sectionKey);
    if (!section) return;
    const card = document.createElement("div");
    card.className = "section-card";
    card.setAttribute("draggable", "true");
    card.dataset.sectionKey = sectionKey;

    const title = document.createElement("div");
    title.className = "section-title";

    const parentCheckbox = document.createElement("input");
    parentCheckbox.type = "checkbox";
    const anyChildrenChecked = section.children.some((child) => config.sections[child.key]);
    const allChildrenChecked = section.children.every((child) => config.sections[child.key]);
    parentCheckbox.checked = anyChildrenChecked;
    parentCheckbox.indeterminate = anyChildrenChecked && !allChildrenChecked;
    parentCheckbox.addEventListener("change", () => {
      const checked = parentCheckbox.checked;
      config.sections[section.key] = checked;
      section.children.forEach((child) => {
        config.sections[child.key] = checked;
      });
      renderSections();
      saveConfig();
    });

    const label = document.createElement("label");
    label.appendChild(parentCheckbox);
    label.append(` ${section.label}`);

    title.appendChild(label);

    const reorder = document.createElement("div");
    reorder.className = "reorder";
    const upBtn = document.createElement("button");
    upBtn.className = "reorder-btn";
    upBtn.textContent = "↑";
    upBtn.title = "Mover para cima";
    upBtn.disabled = sectionOrder[0] === sectionKey;
    upBtn.addEventListener("click", () => moveSection(sectionKey, -1));
    const downBtn = document.createElement("button");
    downBtn.className = "reorder-btn";
    downBtn.textContent = "↓";
    downBtn.title = "Mover para baixo";
    downBtn.disabled = sectionOrder[sectionOrder.length - 1] === sectionKey;
    downBtn.addEventListener("click", () => moveSection(sectionKey, 1));
    reorder.appendChild(upBtn);
    reorder.appendChild(downBtn);
    title.appendChild(reorder);
    card.appendChild(title);

    const children = document.createElement("div");
    children.className = "children";

    section.children.forEach((child) => {
      const childLabel = document.createElement("label");
      const childCheckbox = document.createElement("input");
      childCheckbox.type = "checkbox";
      childCheckbox.checked = config.sections[child.key];
      childCheckbox.addEventListener("change", () => {
        config.sections[child.key] = childCheckbox.checked;
        const anyChecked = section.children.some((c) => config.sections[c.key]);
        config.sections[section.key] = anyChecked;
        renderSections();
        saveConfig();
      });
      childLabel.appendChild(childCheckbox);
      childLabel.append(` ${child.label}`);
      children.appendChild(childLabel);
    });

    card.appendChild(children);
    sectionsContainer.appendChild(card);
  });

  enableDragAndDrop();
}

function setAllSections(value) {
  sectionsSchema.forEach((section) => {
    config.sections[section.key] = value;
    section.children.forEach((child) => {
      config.sections[child.key] = value;
    });
  });
  renderSections();
  saveConfig();
}

enableAllBtn.addEventListener("click", () => setAllSections(true));

async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    if (res.ok) {
      const data = await res.json();
      config = data;
      config.sections = { ...getDefaultConfig(), ...(config.sections || {}) };
      if (Array.isArray(data.section_order) && data.section_order.length) {
        sectionOrder = data.section_order.filter((key) =>
          sectionsSchema.some((section) => section.key === key)
        );
        const missing = sectionsSchema
          .map((section) => section.key)
          .filter((key) => !sectionOrder.includes(key));
        sectionOrder = [...sectionOrder, ...missing];
      }
      if (data.last_json) {
        selectedJson = data.last_json;
        selectedJsonEl.textContent = selectedJson;
      }
      return;
    }
  } catch (err) {
    // ignore
  }
  config.sections = getDefaultConfig();
}

async function saveConfig() {
  const payload = {
    ...config,
    section_order: sectionOrder,
  };
  try {
    await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    // ignore
  }
}

function moveSection(sectionKey, direction) {
  const index = sectionOrder.indexOf(sectionKey);
  if (index === -1) return;
  const newIndex = index + direction;
  if (newIndex < 0 || newIndex >= sectionOrder.length) return;
  sectionOrder.splice(index, 1);
  sectionOrder.splice(newIndex, 0, sectionKey);
  renderSections();
  saveConfig();
}

function enableDragAndDrop() {
  const cards = Array.from(document.querySelectorAll(".section-card"));
  let draggingKey = null;

  cards.forEach((card) => {
    card.addEventListener("dragstart", (e) => {
      draggingKey = card.dataset.sectionKey;
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", draggingKey);
    });

    card.addEventListener("dragend", () => {
      draggingKey = null;
      card.classList.remove("dragging");
      cards.forEach((c) => c.classList.remove("drag-over"));
    });

    card.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      card.classList.add("drag-over");
    });

    card.addEventListener("dragleave", () => {
      card.classList.remove("drag-over");
    });

    card.addEventListener("drop", (e) => {
      e.preventDefault();
      card.classList.remove("drag-over");
      const targetKey = card.dataset.sectionKey;
      const sourceKey = draggingKey || e.dataTransfer.getData("text/plain");
      if (!sourceKey || sourceKey === targetKey) return;
      const from = sectionOrder.indexOf(sourceKey);
      const to = sectionOrder.indexOf(targetKey);
      if (from === -1 || to === -1) return;
      sectionOrder.splice(from, 1);
      sectionOrder.splice(to, 0, sourceKey);
      renderSections();
      saveConfig();
    });
  });
}

function renderJsonList(list) {
  jsonListCache = list || [];
  jsonList.innerHTML = "";
  list.forEach((path) => {
    const item = document.createElement("div");
    item.className = "json-item";
    if (path === selectedJson) item.classList.add("active");
    item.textContent = path;
    item.addEventListener("click", () => {
      selectedJson = path;
      selectedJsonEl.textContent = path;
      renderJsonList(list);
    });
    jsonList.appendChild(item);
  });
}

async function loadJsonList() {
  const res = await fetch("/api/jsons");
  const data = await res.json();
  renderJsonList(data.jsons || []);
}

function handleFile(file) {
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  fetch("/api/upload", { method: "POST", body: formData })
    .then((res) => res.json())
    .then((data) => {
      if (data.path) {
        selectedJson = data.path;
        selectedJsonEl.textContent = selectedJson;
        loadJsonList();
        showToast("JSON carregado.");
      }
    })
    .catch(() => showToast("Falha ao carregar JSON.", false));
}

dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("active");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("active"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("active");
  const file = e.dataTransfer.files[0];
  handleFile(file);
});
fileInput.addEventListener("change", (e) => handleFile(e.target.files[0]));

generateBtn.addEventListener("click", async () => {
  if (!selectedJson) {
    showToast("Selecione um JSON antes de gerar.", false);
    return;
  }
  const payload = {
    json_path: selectedJson,
    sections: config.sections,
  };
  const res = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.ok) {
    showToast("Ficha gerada com sucesso.");
  } else {
    showToast("Falha ao gerar ficha.", false);
  }
});

previewBtn.addEventListener("click", async () => {
  if (!selectedJson) {
    showToast("Selecione um JSON antes da previa.", false);
    return;
  }
  const payload = {
    json_path: selectedJson,
    sections: config.sections,
  };
  const res = await fetch("/api/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.ok) {
    window.open("/preview", "_blank");
    showToast("Previa gerada.");
  } else {
    showToast("Falha ao gerar previa.", false);
  }
});

async function init() {
  await loadConfig();
  renderSections();
  await loadJsonList();
}

init();
