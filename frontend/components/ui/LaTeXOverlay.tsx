"use client";

import katex from "katex";

export default function LaTeXOverlay() {
  const formulas = [
    { label: "ROI", tex: "ROI = \\frac{P_{f} - P_{i}}{P_{i}} \\times 100\\%" },
    { label: "Sharpe", tex: "S = \\frac{R_p - R_f}{\\sigma_p}" },
    { label: "Leverage", tex: "L = \\frac{\\Delta P}{\\Delta E}" },
  ];

  const render = (tex: string) => ({
    __html: katex.renderToString(tex, { throwOnError: false, displayMode: false }),
  });

  return (
    <>
      {formulas.map((f, i) => (
        <div
          key={f.label}
          className="fixed z-20 glass-strong px-4 py-2 rounded-lg hidden lg:block"
          style={{
            top: i === 0 ? "15%" : i === 1 ? "50%" : "85%",
            left: i === 1 ? "3%" : undefined,
            right: i !== 1 ? "3%" : undefined,
            transform: i === 1 ? "translateY(-50%)" : undefined,
          }}
        >
          <div className="text-[10px] font-mono text-white/40 mb-1 tracking-widest">
            {f.label}
          </div>
          <div className="text-sm text-white/80" dangerouslySetInnerHTML={render(f.tex)} />
        </div>
      ))}
    </>
  );
}
