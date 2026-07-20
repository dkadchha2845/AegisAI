/**
 * The hero canvas — a raymarched noise field whose colour and agitation are
 * driven by the current threat level.
 *
 * Two decisions worth defending:
 *
 * 1. **It reads the threat, it does not decorate.** `--threat-color` is
 *    sampled from the document, so the field is the same hue the meter is,
 *    from the same source. When the call goes critical the background goes
 *    with it. A three.js scene that looks pretty but means nothing is the
 *    thing the design tokens explicitly warn against.
 *
 * 2. **It is a single full-screen quad, not a particle system.** One draw
 *    call, no geometry, no per-frame allocation. A hero that costs 40% of the
 *    GPU is a hero that makes the console beside it drop frames, and the
 *    console is the part being judged.
 *
 * Honours prefers-reduced-motion by rendering one static frame and stopping.
 */

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { prefersReducedMotion } from "@/lib/gsap";

const vertexShader = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position, 1.0);
  }
`;

const fragmentShader = /* glsl */ `
  precision highp float;
  varying vec2 vUv;

  uniform float uTime;
  uniform vec2  uMouse;
  uniform vec3  uThreat;      // colour sampled from --threat-color
  uniform float uIntensity;   // 0 calm .. 1 critical
  uniform float uAspect;
  uniform float uLight;       // 0 dark theme, 1 light theme

  // --- simplex noise (Ashima / Gustavson), unmodified -------------------
  vec3 mod289(vec3 x){ return x - floor(x * (1.0/289.0)) * 289.0; }
  vec4 mod289(vec4 x){ return x - floor(x * (1.0/289.0)) * 289.0; }
  vec4 permute(vec4 x){ return mod289(((x*34.0)+1.0)*x); }
  vec4 taylorInvSqrt(vec4 r){ return 1.79284291400159 - 0.85373472095314 * r; }

  float snoise(vec3 v){
    const vec2 C = vec2(1.0/6.0, 1.0/3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
    vec3 i  = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);
    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);
    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;
    i = mod289(i);
    vec4 p = permute(permute(permute(
              i.z + vec4(0.0, i1.z, i2.z, 1.0))
            + i.y + vec4(0.0, i1.y, i2.y, 1.0))
            + i.x + vec4(0.0, i1.x, i2.x, 1.0));
    float n_ = 1.0/7.0;
    vec3 ns = n_ * D.wyz - D.xzx;
    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);
    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);
    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);
    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));
    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);
    vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
    p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
    vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
  }

  float fbm(vec3 p){
    float total = 0.0, amp = 0.5;
    for (int i = 0; i < 4; i++) {
      total += snoise(p) * amp;
      p *= 2.02;
      amp *= 0.5;
    }
    return total;
  }

  void main() {
    vec2 uv = vUv - 0.5;
    uv.x *= uAspect;

    // Speed scales with threat: calm drifts, critical churns. This is the
    // whole point of the piece — motion is a readout, not an idle loop.
    float speed = mix(0.045, 0.28, uIntensity);
    vec2 m = (uMouse - 0.5) * 0.35;
    float n = fbm(vec3(uv * 1.6 + m, uTime * speed));

    // Contour bands. They tighten as threat rises, which reads as pressure.
    float bands = mix(3.0, 9.0, uIntensity);
    float ridge = abs(sin(n * bands + uTime * speed * 2.0));
    ridge = pow(1.0 - ridge, mix(3.0, 1.6, uIntensity));

    // Vignette keeps the centre readable for the headline that sits on top.
    float vignette = smoothstep(1.15, 0.15, length(uv));

    vec3 base = mix(vec3(0.031, 0.035, 0.043), vec3(0.96, 0.965, 0.975), uLight);
    vec3 col = base + uThreat * ridge * vignette * mix(0.55, 0.30, uLight);

    // A touch of the threat hue in the deep field so the whole frame shifts
    // with the level rather than only the bright ridges.
    col += uThreat * 0.05 * vignette * (0.5 + 0.5 * n);

    gl_FragColor = vec4(col, 1.0);
  }
`;

/** Reads a CSS custom property as a THREE.Color. Falling back to the neutral
 *  ink colour matters: before any call starts there is no threat level, and
 *  an unparsed value would otherwise render black. */
function cssColor(name: string, fallback: string): THREE.Color {
  if (typeof window === "undefined") return new THREE.Color(fallback);
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  try {
    return new THREE.Color(value || fallback);
  } catch {
    return new THREE.Color(fallback);
  }
}

const INTENSITY: Record<string, number> = {
  CALM: 0.05,
  WATCH: 0.28,
  ELEVATED: 0.5,
  HIGH: 0.75,
  CRITICAL: 1.0,
};

export function ThreatField({ className }: { className?: string }) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false });
    } catch {
      // No WebGL (remote desktop, locked-down laptop, software rasteriser
      // disabled). The page must still render — the CSS gradient underneath
      // this canvas is the fallback, so we simply do not mount.
      return;
    }
    // Capped at 2: on a 3x phone this is 9x the fragments for no visible gain.
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(host.clientWidth, host.clientHeight);
    host.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.Camera();

    const uniforms = {
      uTime: { value: 0 },
      uMouse: { value: new THREE.Vector2(0.5, 0.5) },
      uThreat: { value: cssColor("--threat-color", "#4d8dff") },
      uIntensity: { value: 0.05 },
      uAspect: { value: host.clientWidth / Math.max(host.clientHeight, 1) },
      uLight: { value: document.documentElement.dataset.theme === "light" ? 1 : 0 },
    };

    const mesh = new THREE.Mesh(
      new THREE.PlaneGeometry(2, 2),
      new THREE.ShaderMaterial({ vertexShader, fragmentShader, uniforms }),
    );
    scene.add(mesh);

    // Target values, eased toward each frame. Snapping the colour on a level
    // change would flash the whole viewport; the meter is allowed to be
    // instant because it is small, the background is not.
    let targetIntensity = uniforms.uIntensity.value;
    let targetColor = uniforms.uThreat.value.clone();

    const syncThreat = () => {
      const level = document.documentElement.dataset.threat ?? "CALM";
      targetIntensity = INTENSITY[level] ?? 0.05;
      targetColor = cssColor("--threat-color", "#4d8dff");
      uniforms.uLight.value =
        document.documentElement.dataset.theme === "light" ? 1 : 0;
    };
    syncThreat();

    // The threat level lives on <html data-threat>, set by whichever screen
    // is driving a call. Observing the attribute avoids threading a prop
    // through every layout component to reach a background.
    const observer = new MutationObserver(syncThreat);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-threat", "data-theme"],
    });

    const onMouse = (e: PointerEvent) => {
      const rect = host.getBoundingClientRect();
      uniforms.uMouse.value.set(
        (e.clientX - rect.left) / rect.width,
        1 - (e.clientY - rect.top) / rect.height,
      );
    };
    window.addEventListener("pointermove", onMouse, { passive: true });

    const onResize = () => {
      const w = host.clientWidth;
      const h = Math.max(host.clientHeight, 1);
      renderer.setSize(w, h);
      uniforms.uAspect.value = w / h;
    };
    const resizeObserver = new ResizeObserver(onResize);
    resizeObserver.observe(host);

    let raf = 0;
    let onScreen = true;
    let lastFrame = 0;
    // rAF's own timestamp rather than THREE.Clock — Clock is deprecated in
    // recent three, and the shader only needs monotonic seconds.
    const started = performance.now();

    // 30fps, not 120. This is a slow-drifting background: at display refresh
    // it burns four times the GPU for motion nobody can distinguish, and on a
    // 120Hz laptop it was starving the compositor badly enough that the page
    // stopped responding to scroll.
    const FRAME_MS = 1000 / 30;

    const render = (now: number) => {
      raf = requestAnimationFrame(render);
      if (!onScreen || now - lastFrame < FRAME_MS) return;
      lastFrame = now;
      uniforms.uTime.value = (now - started) / 1000;
      uniforms.uIntensity.value +=
        (targetIntensity - uniforms.uIntensity.value) * 0.12;
      uniforms.uThreat.value.lerp(targetColor, 0.12);
      renderer.render(scene, camera);
    };

    // Stop entirely once the hero scrolls away. Nothing below the fold is
    // looking at it, and the rest of the page needs the frame budget more.
    const visibility = new IntersectionObserver(
      ([entry]) => {
        onScreen = entry.isIntersecting;
      },
      { threshold: 0 },
    );
    visibility.observe(host);

    if (prefersReducedMotion) {
      // One frame, then stop. Still themed, still coloured by threat, but no
      // motion at all — which is what the preference actually asks for.
      uniforms.uIntensity.value = targetIntensity;
      uniforms.uThreat.value.copy(targetColor);
      renderer.render(scene, camera);
    } else {
      raf = requestAnimationFrame(render);
    }

    // Pause when the tab is hidden. A background eating a GPU while the
    // laptop is on battery in a green room is a real problem.
    const onVisibility = () => {
      if (document.hidden) {
        cancelAnimationFrame(raf);
      } else if (!prefersReducedMotion) {
        raf = requestAnimationFrame(render);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pointermove", onMouse);
      resizeObserver.disconnect();
      visibility.disconnect();
      observer.disconnect();
      mesh.geometry.dispose();
      (mesh.material as THREE.ShaderMaterial).dispose();
      renderer.dispose();
      host.removeChild(renderer.domElement);
    };
  }, []);

  return <div className={`threatfield ${className ?? ""}`} ref={hostRef} aria-hidden="true" />;
}
