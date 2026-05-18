"use client";

import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import { Float, MeshDistortMaterial, Environment } from "@react-three/drei";
import * as THREE from "three";
import { useTrading } from "@/hooks/useTradingContext";

export default function TradingCore({
  scrollProgress,
  section,
}: {
  scrollProgress: number;
  section: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const wireRef = useRef<THREE.Mesh>(null);
  const groupRef = useRef<THREE.Group>(null);
  const { latestTheme } = useTrading();

  const themeColor = useMemo(() => {
    switch (latestTheme) {
      case "profit":
        return new THREE.Color("#4ade80");
      case "loss":
        return new THREE.Color("#f87171");
      default:
        return new THREE.Color("#60a5fa");
    }
  }, [latestTheme]);

  // Section-based transforms
  useFrame((state, delta) => {
    if (!groupRef.current || !meshRef.current || !wireRef.current) return;

    const t = state.clock.elapsedTime;

    // Base rotation
    const baseSpeed = section === 3 ? 8 : 0.5; // Fast spin in PnL section
    meshRef.current.rotation.y += delta * baseSpeed;
    meshRef.current.rotation.x = Math.sin(t * 0.5) * 0.2;
    wireRef.current.rotation.y += delta * baseSpeed;
    wireRef.current.rotation.x = Math.sin(t * 0.5) * 0.2;

    // Scale based on section
    const targetScale = section === 1 ? 1.2 : section === 2 ? 0.6 : 1.0;
    groupRef.current.scale.lerp(
      new THREE.Vector3(targetScale, targetScale, targetScale),
      0.05
    );

    // Position: Section 2 moves to left
    const targetX = section === 2 ? -2.5 : 0;
    groupRef.current.position.lerp(new THREE.Vector3(targetX, 0, 0), 0.05);

    // Color transition
    const mat = meshRef.current.material as THREE.MeshStandardMaterial;
    mat.emissive.lerp(themeColor, 0.03);
    mat.color.lerp(themeColor, 0.03);
  });

  return (
    <group ref={groupRef}>
      <Float speed={2} rotationIntensity={0.5} floatIntensity={0.5}>
        {/* Main Core */}
        <mesh ref={meshRef} castShadow>
          <icosahedronGeometry args={[1.5, 4]} />
          <meshStandardMaterial
            color={themeColor}
            emissive={themeColor}
            emissiveIntensity={0.6}
            roughness={0.2}
            metalness={0.9}
            wireframe={false}
          />
        </mesh>

        {/* Wireframe overlay */}
        <mesh ref={wireRef} scale={1.02}>
          <icosahedronGeometry args={[1.5, 2]} />
          <meshBasicMaterial
            color="#ffffff"
            transparent
            opacity={0.08}
            wireframe
          />
        </mesh>

        {/* Inner glow orb */}
        <mesh scale={0.4}>
          <sphereGeometry args={[1, 32, 32]} />
          <meshBasicMaterial color={themeColor} transparent opacity={0.3} />
        </mesh>

        {/* Orbiting particles */}
        {Array.from({ length: 6 }).map((_, i) => (
          <OrbitingParticle
            key={i}
            index={i}
            color={themeColor}
            radius={2.2 + i * 0.3}
            speed={0.5 + i * 0.2}
          />
        ))}
      </Float>

      <Environment preset="city" />
      <ambientLight intensity={0.2} />
      <pointLight position={[5, 5, 5]} intensity={1} color={themeColor} />
      <pointLight position={[-5, -5, -5]} intensity={0.5} color="#c4b5fd" />
    </group>
  );
}

function OrbitingParticle({
  index,
  color,
  radius,
  speed,
}: {
  index: number;
  color: THREE.Color;
  radius: number;
  speed: number;
}) {
  const ref = useRef<THREE.Mesh>(null);

  useFrame(({ clock }) => {
    if (!ref.current) return;
    const t = clock.elapsedTime * speed + index;
    ref.current.position.x = Math.cos(t) * radius;
    ref.current.position.z = Math.sin(t) * radius;
    ref.current.position.y = Math.sin(t * 1.5) * 0.5;
  });

  return (
    <mesh ref={ref}>
      <sphereGeometry args={[0.04, 8, 8]} />
      <meshBasicMaterial color={color} transparent opacity={0.8} />
    </mesh>
  );
}
