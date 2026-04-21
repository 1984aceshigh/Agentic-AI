(function () {
  if (typeof window === "undefined") {
    return;
  }

  const previewNodes = document.querySelectorAll(".js-markdown-mermaid-preview");
  if (!previewNodes.length) {
    return;
  }

  const looksLikeMermaid = (text) => {
    const trimmed = (text || "").trim();
    if (!trimmed) {
      return false;
    }

    return /^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram|erDiagram|journey|gantt|pie|mindmap|timeline|gitGraph|quadrantChart|requirementDiagram|C4Context|C4Container|C4Component|C4Dynamic|C4Deployment)\b/i.test(
      trimmed,
    );
  };

  const sanitizeHtml = (html) => {
    if (window.DOMPurify && typeof window.DOMPurify.sanitize === "function") {
      return window.DOMPurify.sanitize(html);
    }
    return html;
  };

  const normalizePreviewText = (text) => {
    return (text || "")
      .replace(/\r\n?/g, "\n")
      .split("\n")
      .map((line) => line.replace(/[\t ]+$/g, ""))
      .join("\n");
  };

  const normalizeMermaidText = (text) => {
    let normalized = normalizePreviewText(text)
      .replace(/\n[\t ]*\n[\t\n ]+/g, "\n\n")
      .trim();

    for (let i = 0; i < 3; i += 1) {
      const wrappedMatch = normalized.match(/^```\s*[a-zA-Z0-9_+-]*\s*\n([\s\S]*?)\n```\s*$/);
      if (!wrappedMatch) {
        break;
      }
      normalized = normalizePreviewText(wrappedMatch[1] || "").trim();
    }

    normalized = normalized
      .replace(/\n[\t ]*\n[\t\n ]+/g, "\n\n")
      .trim();

    normalized = normalized.replace(/^```\s*[a-zA-Z0-9_+-]*\s*\n/i, "");
    normalized = normalized.replace(/\n```\s*$/i, "");

    normalized = normalized.replace(/^workflow(\s+(TD|LR|BT|RL)\b)/i, "flowchart$1");
    normalized = normalized.replace(/^(mermaid|markdown_mermaid)\s*\n/i, "");
    return normalized;
  };

  const extractFencedMermaidBlocks = (text) => {
    const blocks = [];
    const source = text || "";
    const regex = /```mermaid\s*([\s\S]*?)```/gi;
    let match = regex.exec(source);
    while (match) {
      const block = normalizeMermaidText(match[1] || "");
      if (block) {
        blocks.push(block);
      }
      match = regex.exec(source);
    }
    return blocks;
  };

  const replaceMermaidNodeWithSource = (mermaidNode, fallbackSource = "") => {
    const source = normalizeMermaidText(
      fallbackSource || mermaidNode.dataset.originalSource || mermaidNode.textContent || "",
    );
    const pre = document.createElement("pre");
    pre.className = "code-block";
    pre.textContent = `\`\`\`mermaid\n${source}\n\`\`\``;
    mermaidNode.replaceWith(pre);
  };

  const updateToggleState = (previewNode) => {
    const previewId = previewNode.id;
    if (!previewId) {
      return;
    }

    const toggleButton = document.querySelector(`.js-preview-toggle[data-target="${previewId}"]`);
    if (!toggleButton) {
      return;
    }

    if (!previewNode.classList.contains("is-collapsed")) {
      toggleButton.hidden = false;
      toggleButton.textContent = "折りたたむ";
      return;
    }

    const hasOverflow = previewNode.scrollHeight > previewNode.clientHeight + 1;
    toggleButton.hidden = !hasOverflow;
    toggleButton.textContent = "全文表示";
  };

  if (window.marked && typeof window.marked.setOptions === "function") {
    window.marked.setOptions({
      gfm: true,
      breaks: false,
    });
  }

  previewNodes.forEach((node) => {
    const rawText = normalizePreviewText(node.textContent || "");
    const fencedBlocks = extractFencedMermaidBlocks(rawText);

    if (fencedBlocks.length > 0) {
      const fragment = document.createDocumentFragment();
      fencedBlocks.forEach((block) => {
        const mermaidContainer = document.createElement("div");
        mermaidContainer.className = "mermaid";
        mermaidContainer.textContent = block;
        mermaidContainer.dataset.originalSource = block;
        fragment.appendChild(mermaidContainer);
      });
      node.replaceChildren(fragment);
      updateToggleState(node);
      return;
    }

    if (looksLikeMermaid(rawText)) {
      const mermaidContainer = document.createElement("div");
      mermaidContainer.className = "mermaid";
      mermaidContainer.textContent = normalizeMermaidText(rawText);
      mermaidContainer.dataset.originalSource = mermaidContainer.textContent;
      node.replaceChildren(mermaidContainer);
      updateToggleState(node);
      return;
    }

    if (window.marked && typeof window.marked.parse === "function") {
      const html = window.marked.parse(rawText);
      node.innerHTML = sanitizeHtml(html);
    } else {
      node.textContent = rawText;
    }

    node.querySelectorAll("pre > code.language-mermaid, pre > code.lang-mermaid").forEach((codeNode) => {
      const preNode = codeNode.parentElement;
      if (!preNode || !preNode.parentElement) {
        return;
      }

      const mermaidContainer = document.createElement("div");
      mermaidContainer.className = "mermaid";
      mermaidContainer.textContent = normalizeMermaidText(codeNode.textContent || "");
      mermaidContainer.dataset.originalSource = mermaidContainer.textContent;
      preNode.parentElement.replaceChild(mermaidContainer, preNode);
    });

    updateToggleState(node);
  });

  document.querySelectorAll(".js-preview-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const targetId = button.getAttribute("data-target");
      if (!targetId) {
        return;
      }

      const targetNode = document.getElementById(targetId);
      if (!targetNode) {
        return;
      }

      const isCollapsed = targetNode.classList.toggle("is-collapsed");
      button.textContent = isCollapsed ? "全文表示" : "折りたたむ";
    });
  });

  if (window.mermaid) {
    try {
      window.mermaid.initialize({
        startOnLoad: false,
        securityLevel: "loose",
      });

      const mermaidNodes = Array.from(document.querySelectorAll(".js-markdown-mermaid-preview .mermaid"));

      const renderNodesSafely = async () => {
        const canRenderDirectly = typeof window.mermaid.render === "function";
        const canRun = typeof window.mermaid.run === "function";
        if (!canRenderDirectly && !canRun) {
          return;
        }

        let renderSeq = 0;
        for (const mermaidNode of mermaidNodes) {
          const source = normalizeMermaidText(
            mermaidNode.dataset.originalSource || mermaidNode.textContent || "",
          );
          mermaidNode.dataset.originalSource = source;

          try {
            if (canRenderDirectly) {
              renderSeq += 1;
              const renderId = `node-detail-mermaid-${Date.now()}-${renderSeq}`;
              const rendered = await window.mermaid.render(renderId, source);
              if (typeof rendered === "string") {
                mermaidNode.innerHTML = rendered;
              } else if (rendered && typeof rendered.svg === "string") {
                mermaidNode.innerHTML = rendered.svg;
                if (typeof rendered.bindFunctions === "function") {
                  rendered.bindFunctions(mermaidNode);
                }
              } else {
                throw new Error("Unexpected mermaid.render result");
              }
            } else {
              mermaidNode.textContent = source;
              await window.mermaid.run({ nodes: [mermaidNode] });
            }
          } catch (_error) {
            replaceMermaidNodeWithSource(mermaidNode, source);
          }
        }
      };

      renderNodesSafely()
        .finally(() => {
          previewNodes.forEach((previewNode) => {
            updateToggleState(previewNode);
          });
        });
    } catch (error) {
      console.warn("Failed to render mermaid preview", error);
    }
  }
})();