export default function AuroraBackground() {
  return (
    <div
      className="fixed inset-0 -z-10 bg-[#030303] overflow-hidden pointer-events-none"
      style={{ willChange: "transform", transform: "translateZ(0)" }}
    >
      <div
        className="absolute -top-[20%] -left-[10%] w-[70vw] h-[70vw] rounded-full mix-blend-screen"
        style={{
          background: "radial-gradient(circle, #4c1d95 0%, transparent 70%)",
          filter: "blur(120px)",
          opacity: 0.25,
          animation: "blob 18s infinite alternate",
        }}
      />
      <div
        className="absolute top-[30%] -right-[10%] w-[60vw] h-[60vw] rounded-full mix-blend-screen"
        style={{
          background: "radial-gradient(circle, #1e3a8a 0%, transparent 70%)",
          filter: "blur(100px)",
          opacity: 0.2,
          animation: "blob 22s infinite alternate-reverse",
        }}
      />
      <div
        className="absolute -bottom-[10%] left-[20%] w-[50vw] h-[50vw] rounded-full mix-blend-screen"
        style={{
          background: "radial-gradient(circle, #0891b2 0%, transparent 70%)",
          filter: "blur(90px)",
          opacity: 0.15,
          animation: "blob 20s infinite alternate",
        }}
      />
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          opacity: 0.04,
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 400 400' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
        }}
      />
    </div>
  );
}
