import { Suspense } from "react";
import HomeContent from "./HomeContent";

export default function Page() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#030303]" />}>
      <HomeContent />
    </Suspense>
  );
}
