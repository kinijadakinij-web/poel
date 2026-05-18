"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

interface OrbCoreProps {
  color?: string;       // hex string e.g. "#60a5fa"
  section?: number;
  size?: number;        // canvas size in px
}

export default function OrbCore({ color = "#60a5fa", section = 0, size = 220 }: OrbCoreProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<{
    mat:  THREE.LineBasicMaterial;
    mmat: THREE.LineBasicMaterial;
    imat: THREE.MeshBasicMaterial;
    rmat: THREE.LineBasicMaterial;
    pm:   THREE.PointsMaterial;
    renderer: THREE.WebGLRenderer;
  } | null>(null);

  // Re-colour when prop changes
  useEffect(() => {
    if (!stateRef.current) return;
    const hex = new THREE.Color(color).getHex();
    const { mat, mmat, imat, rmat, pm } = stateRef.current;
    mat.color.setHex(hex);
    mmat.color.setHex(hex);
    imat.color.setHex(hex);
    rmat.color.setHex(hex);
    pm.color.setHex(hex);
  }, [color]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const W = canvas.offsetWidth || size;
    const H = canvas.offsetHeight || size;

    const scene    = new THREE.Scene();
    const camera   = new THREE.PerspectiveCamera(55, W / H, 0.1, 1000);
    camera.position.z = 3.2;

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setSize(W, H);
    renderer.setClearColor(0x000000, 0);

    const hex = new THREE.Color(color).getHex();

    // Outer wireframe orb
    const geo  = new THREE.IcosahedronGeometry(1.1, 3);
    const wgeo = new THREE.WireframeGeometry(geo);
    const mat  = new THREE.LineBasicMaterial({ color: hex, opacity: 0.35, transparent: true });
    const orb  = new THREE.LineSegments(wgeo, mat);
    scene.add(orb);

    // Mid orb
    const mgeo  = new THREE.IcosahedronGeometry(0.75, 1);
    const mwgeo = new THREE.WireframeGeometry(mgeo);
    const mmat  = new THREE.LineBasicMaterial({ color: hex, opacity: 0.2, transparent: true });
    const morb  = new THREE.LineSegments(mwgeo, mmat);
    scene.add(morb);

    // Inner glow wireframe sphere
    const igeo = new THREE.SphereGeometry(0.35, 16, 16);
    const imat = new THREE.MeshBasicMaterial({ color: hex, opacity: 0.15, transparent: true, wireframe: true });
    const iorb = new THREE.Mesh(igeo, imat);
    scene.add(iorb);

    // Ring
    const rgeo = new THREE.TorusGeometry(1.5, 0.003, 2, 100);
    const rmat = new THREE.LineBasicMaterial({ color: hex, opacity: 0.18, transparent: true });
    const ring = new THREE.Mesh(rgeo, rmat);
    ring.rotation.x = Math.PI / 3;
    scene.add(ring);

    // Particles
    const N   = 400;
    const pg  = new THREE.BufferGeometry();
    const pos = new Float32Array(N * 3);
    for (let i = 0; i < N * 3; i++) pos[i] = (Math.random() - 0.5) * 9;
    pg.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    const pm  = new THREE.PointsMaterial({ color: hex, size: 0.025, opacity: 0.4, transparent: true });
    const pts = new THREE.Points(pg, pm);
    scene.add(pts);

    // Store refs for colour updates
    stateRef.current = { mat, mmat, imat, rmat, pm, renderer };

    const clock = new THREE.Clock();
    let rafId: number;

    function animate() {
      rafId = requestAnimationFrame(animate);
      const t  = clock.getElapsedTime();
      // Use section prop instead of window.scrollY — section 0→3 maps to 0→1
      const sp = section / 3;
      const scale = 1 - sp * 0.25;

      orb.scale.setScalar(scale * (1 + Math.sin(t * 1.8) * 0.02));
      morb.scale.setScalar(scale * 0.65 * (1 + Math.cos(t * 2.4) * 0.025));
      iorb.scale.setScalar(scale * 0.3);

      const rs = 0.004 + sp * 0.012;
      orb.rotation.y  += rs;
      orb.rotation.x  += rs * 0.4;
      morb.rotation.y -= rs * 0.8;
      morb.rotation.z += rs * 0.3;
      iorb.rotation.y += rs * 1.5;
      ring.rotation.z += 0.002;
      pts.rotation.y  += 0.0004;
      pts.rotation.x  += 0.0002;

      renderer.render(scene, camera);
    }
    animate();

    const ro = new ResizeObserver(() => {
      const W2 = canvas.offsetWidth;
      const H2 = canvas.offsetHeight;
      if (!W2 || !H2) return;
      camera.aspect = W2 / H2;
      camera.updateProjectionMatrix();
      renderer.setSize(W2, H2);
    });
    ro.observe(canvas);

    return () => {
      cancelAnimationFrame(rafId);
      ro.disconnect();
      renderer.dispose();
      stateRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // init once; color + section handled via separate effects

  // Update speed/scale based on section without reinit
  const sectionRef = useRef(section);
  useEffect(() => { sectionRef.current = section; }, [section]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: size, height: size, display: "block" }}
    />
  );
}
