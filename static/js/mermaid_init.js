(function () {
  if (typeof window === "undefined") {
    return;
  }

  if (typeof window.mermaid === "undefined") {
    return;
  }

  window.mermaid.initialize({
    startOnLoad: true,
    securityLevel: "loose",
  });
})();
