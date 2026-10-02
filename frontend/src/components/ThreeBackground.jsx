import { useEffect, useRef } from "react";
import * as THREE from "three";

// Ambient backdrop. Deliberately quiet: slow drift, no mouse parallax, capped
// frame rate, paused in hidden tabs, and a single still frame when the user
// prefers reduced motion. `subdued` dims it further while a mission is shown.
const FRAME_INTERVAL_MS = 1000 / 24;

export default function ThreeBackground({ subdued = false }) {
  const containerRef = useRef(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.z = 18;

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false, powerPreference: "low-power" });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    container.appendChild(renderer.domElement);

    const mainGroup = new THREE.Group();
    scene.add(mainGroup);

    const coreGeometry = new THREE.IcosahedronGeometry(4.5, 2);
    const coreMaterial = new THREE.MeshBasicMaterial({ color: 0x8b5cf6, wireframe: true, transparent: true, opacity: 0.08 });
    const coreMesh = new THREE.Mesh(coreGeometry, coreMaterial);
    mainGroup.add(coreMesh);

    const ringGeometry = new THREE.TorusGeometry(7.5, 0.025, 12, 90);
    const ringMaterial = new THREE.MeshBasicMaterial({ color: 0x3b82f6, transparent: true, opacity: 0.1 });
    const ringMesh = new THREE.Mesh(ringGeometry, ringMaterial);
    ringMesh.rotation.x = Math.PI / 3;
    ringMesh.rotation.y = Math.PI / 6;
    mainGroup.add(ringMesh);

    const particleCount = 120;
    const particleGeometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    for (let i = 0; i < particleCount; i++) {
      const radius = 9 + Math.random() * 15;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(Math.random() * 2 - 1);
      positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
      positions[i * 3 + 2] = radius * Math.cos(phi);
    }
    particleGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const particleMaterial = new THREE.PointsMaterial({ size: 0.16, color: 0x67e8f9, transparent: true, opacity: 0.35 });
    const particles = new THREE.Points(particleGeometry, particleMaterial);
    mainGroup.add(particles);

    const clock = new THREE.Clock();
    let animationFrameId;
    let lastFrame = 0;

    const draw = () => {
      const t = clock.getElapsedTime();
      coreMesh.rotation.y = t * 0.025;
      coreMesh.rotation.x = t * 0.015;
      ringMesh.rotation.z = t * 0.012;
      particles.rotation.y = t * 0.006;
      renderer.render(scene, camera);
    };

    const animate = (now) => {
      animationFrameId = requestAnimationFrame(animate);
      if (document.hidden || now - lastFrame < FRAME_INTERVAL_MS) return;
      lastFrame = now;
      draw();
    };

    if (reduceMotion) draw();
    else animationFrameId = requestAnimationFrame(animate);

    const handleResize = () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
      if (reduceMotion) draw();
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animationFrameId);
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement);
      coreGeometry.dispose();
      coreMaterial.dispose();
      ringGeometry.dispose();
      ringMaterial.dispose();
      particleGeometry.dispose();
      particleMaterial.dispose();
      renderer.dispose();
    };
  }, []);

  return <div ref={containerRef} className={`bg-3d-canvas ${subdued ? "bg-3d-subdued" : ""}`} />;
}
