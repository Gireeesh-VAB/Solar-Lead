"use client";

// The result page's 3D rooftop viewer: a client-side Three.js/React Three
// Fiber scene built directly from backend/src/solarfit/engine/panorama.py::
// build_scene_geometry()'s roof/walls/panels/mounting/obstacle vertex/face
// arrays (the same real DSM/segment-plane/panel-layout geometry the .glb
// pipeline used — see git history for PanoramaViewer.tsx, since replaced by
// this component), instead of loading a pre-baked .glb.
//
// The REAL building (roof/walls/panels/mounting/obstacles) below is
// unchanged geometry — every vertex/face comes straight from the backend,
// exactly as calculated. Everything under "presentation only" further down
// (facade texture, ground, road, neighbouring buildings, trees, sky) is
// decor: procedurally generated on a <canvas> at runtime, not a real
// building photo, and deliberately placed outside the real building's own
// footprint so it never touches or substitutes for real geometry/data.
import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Environment, OrbitControls, Sky } from "@react-three/drei";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import * as THREE from "three";
import type { SceneMeshDto, SceneObstacleDto } from "@/lib/api/client";

function meshGeometry(mesh: SceneMeshDto): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(mesh.vertices.length * 3);
  mesh.vertices.forEach(([x, y, z], i) => {
    positions[i * 3] = x;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = z;
  });
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));

  if (mesh.colors) {
    const colors = new Float32Array(mesh.colors.length * 3);
    mesh.colors.forEach(([r, g, b], i) => {
      colors[i * 3] = r;
      colors[i * 3 + 1] = g;
      colors[i * 3 + 2] = b;
    });
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  }

  geometry.setIndex(mesh.faces.flat());
  geometry.computeVertexNormals();
  return geometry;
}

/** engine/panorama.py builds Z-up (z = elevation); three.js's default
 *  camera/OrbitControls setup assumes Y-up. Rotating the whole group -90°
 *  about X is the same fix _gltf_y_up() applies for the .glb export,
 *  applied here as a scene-graph transform instead of a node matrix. */
const Z_UP_TO_Y_UP = [-Math.PI / 2, 0, 0] as const;

/** Same -90° X rotation as Z_UP_TO_Y_UP above, applied to a single point
 *  instead of the mesh group — lets camera-preset math and the
 *  presentation-only decor below work in the backend's own local frame
 *  (x east, y north, z up) and convert to the world space the Canvas's
 *  camera/undotated siblings actually live in. */
function localToWorld([x, y, z]: [number, number, number]): [number, number, number] {
  return [x, z, -y];
}

// ---------------------------------------------------------------------------
// Presentation only, below this line: procedural (canvas-drawn) textures and
// decorative props. None of this reads backend geometry beyond the real
// building's own center/radius (to place decor sensibly around it) — no
// roof/wall/panel/mounting/obstacle vertex or face is touched, added, or
// removed.
// ---------------------------------------------------------------------------

/** A tileable dummy facade texture — a plaster base with terracotta/brick
 *  vertical accent bands, a grid of windows with a glass gradient, and a
 *  balcony shadow line, drawn on an offscreen canvas at runtime. Styled
 *  after a typical mid-rise Indian apartment facade (reference image
 *  reviewed 2026-09-10) but explicitly a stylized stand-in — not a real
 *  building photo — so it never reads as authoritative imagery of the
 *  actual property. */
function useFacadeTexture(
  baseColor: string,
  accentColor: string,
  windowColor: string,
  rows: number,
  cols: number
) {
  return useMemo(() => {
    const size = 512;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    if (!ctx) return new THREE.Texture();

    ctx.fillStyle = baseColor;
    ctx.fillRect(0, 0, size, size);

    const cellW = size / cols;
    const cellH = size / rows;

    // Vertical terracotta/brick accent bands every third bay — the
    // reference's most visually distinctive facade cue.
    for (let c = 0; c < cols; c++) {
      if (c % 3 !== 1) continue;
      ctx.fillStyle = accentColor;
      ctx.fillRect(c * cellW, 0, cellW, size);
    }

    const pad = Math.min(cellW, cellH) * 0.16;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const x = c * cellW;
        const y = r * cellH;
        const isAccentBay = c % 3 === 1;

        // Window glass, with a soft vertical gradient for a hint of
        // reflection instead of a flat fill.
        const glassGrad = ctx.createLinearGradient(0, y, 0, y + cellH);
        glassGrad.addColorStop(0, windowColor);
        glassGrad.addColorStop(1, "rgba(20,28,38,0.9)");
        ctx.fillStyle = glassGrad;
        const winW = isAccentBay ? cellW - pad * 3.2 : cellW - pad * 2;
        const winX = isAccentBay ? x + pad * 1.6 : x + pad;
        ctx.fillRect(winX, y + pad, winW, cellH - pad * 2.8);

        // Window frame.
        ctx.strokeStyle = "rgba(255,255,255,0.3)";
        ctx.lineWidth = 2;
        ctx.strokeRect(winX, y + pad, winW, cellH - pad * 2.8);

        // Balcony ledge shadow beneath each window band.
        const shadowGrad = ctx.createLinearGradient(0, y + cellH - pad * 1.6, 0, y + cellH - pad * 0.6);
        shadowGrad.addColorStop(0, "rgba(30,26,20,0.5)");
        shadowGrad.addColorStop(1, "rgba(30,26,20,0.05)");
        ctx.fillStyle = shadowGrad;
        ctx.fillRect(x + pad * 0.4, y + cellH - pad * 1.6, cellW - pad * 0.8, pad * 1.0);

        // Balcony rail line.
        ctx.strokeStyle = "rgba(70,65,55,0.55)";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(x + pad * 0.4, y + cellH - pad * 0.7);
        ctx.lineTo(x + cellW - pad * 0.4, y + cellH - pad * 0.7);
        ctx.stroke();
      }
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
  }, [baseColor, accentColor, windowColor, rows, cols]);
}

/** A tileable ground texture — mottled concrete/paving, not grass, since a
 *  dense residential rooftop context reads more realistically as a paved
 *  courtyard/street than a lawn. */
function useGroundTexture() {
  // Lazy useState initializer rather than useMemo(..., []): this has no
  // reactive inputs, so it only ever needs to run once per mount, and the
  // React Compiler flags a zero-dependency useMemo wrapping canvas/DOM
  // calls as unsafe to preserve.
  const [texture] = useState(() => {
    const size = 256;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    if (!ctx) return new THREE.Texture();

    ctx.fillStyle = "#a89c84";
    ctx.fillRect(0, 0, size, size);
    // Deterministic pseudo-random speckle (sin-hash, not Math.random) so
    // this stays a pure function of its inputs — required for a value
    // computed during render.
    const rng = (seed: number) => {
      const v = Math.sin(seed * 12.9898) * 43758.5453;
      return v - Math.floor(v);
    };
    for (let i = 0; i < 900; i++) {
      const shade = 130 + Math.floor(rng(i) * 40);
      ctx.fillStyle = `rgba(${shade},${shade},${shade - 6},0.5)`;
      const x = rng(i + 900) * size;
      const y = rng(i + 1800) * size;
      ctx.fillRect(x, y, 1.5, 1.5);
    }
    const created = new THREE.CanvasTexture(canvas);
    created.wrapS = THREE.RepeatWrapping;
    created.wrapT = THREE.RepeatWrapping;
    created.colorSpace = THREE.SRGBColorSpace;
    return created;
  });
  return texture;
}

// Real-world scale for the facade texture's UV mapping, so a window "bay"
// and "floor" read as actual building proportions instead of tiling
// densely enough to look like a 20-storey tower on a 16 m building (the
// bug a reference-image review caught, 2026-09-10).
const FACADE_ROWS = 3;
const FACADE_COLS = 9;
const METERS_PER_FLOOR = 3.0;
const METERS_PER_BAY = 3.4;

/** The real wall mesh, textured with the dummy facade above. UVs are
 *  synthesised here from each vertex's real position (arc length around
 *  the building's own centroid for U, real elevation for V, both scaled
 *  to real-world metres per bay/floor) purely to map the texture — the
 *  underlying positions/faces are the exact backend mesh, untouched.
 *  Vertex colors (the backend's own warm-masonry wall tint) are kept and
 *  multiplied with the texture rather than dropped. */
function TexturedBuildingMesh({
  mesh,
  center,
  radius,
}: {
  mesh: SceneMeshDto;
  center: [number, number, number];
  radius: number;
}) {
  const texture = useFacadeTexture("#e2dcce", "#a9694a", "#3a4b5c", FACADE_ROWS, FACADE_COLS);

  const geometry = useMemo(() => {
    const geo = meshGeometry(mesh);
    const [cx, cy] = center;
    const uvs = new Float32Array(mesh.vertices.length * 2);
    const uPerTile = FACADE_COLS * METERS_PER_BAY;
    const vPerTile = FACADE_ROWS * METERS_PER_FLOOR;
    mesh.vertices.forEach(([x, y, z], i) => {
      const angle = Math.atan2(y - cy, x - cx);
      const arcLength = angle * radius;
      uvs[i * 2] = arcLength / uPerTile;
      uvs[i * 2 + 1] = z / vPerTile;
    });
    geo.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
    return geo;
  }, [mesh, center, radius]);

  return (
    <mesh geometry={geometry} castShadow receiveShadow>
      <meshStandardMaterial
        map={texture}
        vertexColors={!!mesh.colors}
        side={THREE.DoubleSide}
        roughness={0.8}
      />
    </mesh>
  );
}

/** One simple neighbouring building — a plain box with the same dummy
 *  facade treatment, at a fixed, deliberately non-real height/position.
 *  Purely contextual decor so the viewer can read "this is a rooftop in a
 *  built-up area" — never meant to depict any specific real neighbour. */
function NeighbourBuilding({
  position,
  width,
  depth,
  height,
  tint,
}: {
  position: [number, number, number];
  width: number;
  depth: number;
  height: number;
  tint: string;
}) {
  const texture = useFacadeTexture(tint, "#9c6449", "#3a4b5c", FACADE_ROWS, FACADE_COLS);
  // A box's default UVs span 0..1 per face regardless of its real size —
  // without this, a tall neighbour shows the same few windows stretched
  // over its whole height instead of tiling at a real floor/bay scale.
  const repeated = useMemo(() => {
    const t = texture.clone();
    t.repeat.set(
      Math.max(1, Math.round((width + depth) / (FACADE_COLS * METERS_PER_BAY))),
      Math.max(1, Math.round(height / (FACADE_ROWS * METERS_PER_FLOOR)))
    );
    t.needsUpdate = true;
    return t;
  }, [texture, width, depth, height]);
  return (
    <mesh position={[position[0], height / 2, position[2]]} receiveShadow>
      <boxGeometry args={[width, height, depth]} />
      <meshStandardMaterial map={repeated} roughness={0.85} />
    </mesh>
  );
}

/** A simple low-poly tree (trunk + a layered, offset foliage cluster) —
 *  decor only. Three staggered, laterally-offset cone layers instead of
 *  one stacked column reads as a fuller, less obviously-procedural
 *  canopy, closer to the dense tree cover in the reviewed reference
 *  image (2026-09-10) than a single Christmas-tree cone. */
function Tree({
  position,
  scale = 1,
  tint = "#3f6b3f",
}: {
  position: [number, number, number];
  scale?: number;
  tint?: string;
}) {
  return (
    <group position={position} scale={scale}>
      <mesh position={[0, 0.9, 0]} castShadow>
        <cylinderGeometry args={[0.12, 0.16, 1.8, 6]} />
        <meshStandardMaterial color="#5c4430" roughness={0.95} />
      </mesh>
      <mesh position={[0.15, 2.1, 0.1]} castShadow>
        <coneGeometry args={[1.15, 2.3, 8]} />
        <meshStandardMaterial color={tint} roughness={0.95} />
      </mesh>
      <mesh position={[-0.25, 2.6, -0.15]} castShadow>
        <coneGeometry args={[0.95, 2.0, 8]} />
        <meshStandardMaterial color={tint} roughness={0.95} />
      </mesh>
      <mesh position={[0.1, 3.3, 0.2]} castShadow>
        <coneGeometry args={[0.7, 1.5, 8]} />
        <meshStandardMaterial color={tint} roughness={0.95} />
      </mesh>
    </group>
  );
}

/** Ground, an access road, a handful of neighbouring buildings and trees —
 *  all sized off and placed around the REAL building's own center/radius
 *  (from the actual roof geometry) so the scene stays proportionate, but
 *  none of it is real measured data. Positions are seeded once (useMemo)
 *  so they stay put across re-renders instead of jittering. */
function SiteContext({ worldCenter, radius }: { worldCenter: [number, number, number]; radius: number }) {
  const groundTexture = useGroundTexture();
  const [cx, , cz] = worldCenter;
  const groundSize = Math.max(radius * 12, 80);

  const neighbours = useMemo(() => {
    const rng = (seed: number) => {
      const x = Math.sin(seed * 999.7) * 43758.5453;
      return x - Math.floor(x);
    };
    const configs: {
      position: [number, number, number];
      width: number;
      depth: number;
      height: number;
      tint: string;
    }[] = [];
    const tints = ["#d8cdb8", "#c7bfae", "#d3c6ae", "#bdb49f"];
    const angles = [0.5, 1.6, 2.7, 3.6, 4.6, 5.6];
    angles.forEach((a, i) => {
      const dist = radius * (3.2 + rng(i) * 2.2);
      const width = radius * (0.9 + rng(i + 10) * 0.8);
      const depth = radius * (0.9 + rng(i + 20) * 0.8);
      const height = 6 + rng(i + 30) * 16;
      configs.push({
        position: [cx + Math.cos(a) * dist, 0, cz + Math.sin(a) * dist],
        width,
        depth,
        height,
        tint: tints[i % tints.length],
      });
    });
    return configs;
  }, [cx, cz, radius]);

  const trees = useMemo(() => {
    const rng = (seed: number) => {
      const x = Math.sin(seed * 12.9898) * 43758.5453;
      return x - Math.floor(x);
    };
    const tints = ["#3f6b3f", "#4d7a4a", "#3a5f42", "#527d4e"];
    const positions: { position: [number, number, number]; scale: number; tint: string }[] = [];
    // Denser, closer-in canopy than the first pass — closer to the
    // heavily tree-lined reference image than a sparse ring of 10.
    for (let i = 0; i < 22; i++) {
      const angle = rng(i) * Math.PI * 2;
      const dist = radius * (1.35 + rng(i + 50) * 2.1);
      positions.push({
        position: [cx + Math.cos(angle) * dist, 0, cz + Math.sin(angle) * dist],
        scale: 0.8 + rng(i + 70) * 0.75,
        tint: tints[i % tints.length],
      });
    }
    return positions;
  }, [cx, cz, radius]);

  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[cx, 0, cz]} receiveShadow>
        <planeGeometry args={[groundSize, groundSize]} />
        <meshStandardMaterial map={groundTexture} roughness={1} />
      </mesh>

      {/* Access road strip along one side of the plot. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[cx + radius * 3.4, 0.01, cz]} receiveShadow>
        <planeGeometry args={[radius * 2.2, groundSize * 0.9]} />
        <meshStandardMaterial color="#4a4a48" roughness={0.95} />
      </mesh>

      {neighbours.map((n, i) => (
        <NeighbourBuilding key={i} {...n} />
      ))}
      {trees.map((t, i) => (
        <Tree key={i} position={t.position} scale={t.scale} tint={t.tint} />
      ))}
    </group>
  );
}

// ---------------------------------------------------------------------------
// Real building geometry, unchanged from the backend below this line.
// ---------------------------------------------------------------------------

/** Real per-vertex colour (roof sunshine tint, panel frame/glass, mounting
 *  rack steel, an obstacle's flat tint) when the backend sent one; a flat
 *  fallback material colour otherwise — never a fabricated gradient
 *  standing in for real shading data. */
function VertexColoredMesh({ mesh, fallbackColor }: { mesh: SceneMeshDto; fallbackColor: string }) {
  const geometry = useMemo(() => meshGeometry(mesh), [mesh]);
  return (
    <mesh geometry={geometry} castShadow receiveShadow>
      <meshStandardMaterial
        vertexColors={!!mesh.colors}
        color={mesh.colors ? "#ffffff" : fallbackColor}
        side={THREE.DoubleSide}
        roughness={0.85}
      />
    </mesh>
  );
}

function RoofSurface({ mesh }: { mesh: SceneMeshDto }) {
  return <VertexColoredMesh mesh={mesh} fallbackColor="#8a94a6" />;
}

// ---------------------------------------------------------------------------
// Panel rendering: two materials instead of one, real per-panel UV.
//
// engine/panorama.py::_panel_module() builds every module the same fixed
// way — a frame box (8 vertices, 12 triangles) immediately followed by a
// glass box (8 vertices, 12 triangles), concatenated in that order. That
// layout is stable and already load-bearing in the backend's own test
// suite (VERTICES_PER_PANEL/FACES_PER_PANEL in test_panorama.py), so the
// viewer exploits it here to split the one merged `panels` mesh back into
// a frame sub-mesh and a glass sub-mesh, purely for rendering: two
// materials (satin aluminium vs glossy laminate) read as a real module far
// better than one flat-shaded colour, and a real module boundary is what
// makes adjacent panels individually identifiable instead of fusing into
// one blue slab. No vertex is added, removed, or moved — every position
// comes straight from the backend, unchanged.
// ---------------------------------------------------------------------------

type Vec3 = [number, number, number];

const sub3 = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const cross3 = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
const dot3 = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const len3 = (a: Vec3) => Math.sqrt(dot3(a, a));
const norm3 = (a: Vec3): Vec3 => {
  const l = len3(a);
  return l > 1e-9 ? [a[0] / l, a[1] / l, a[2] / l] : [0, 0, 1];
};

const PANEL_VERTEX_STRIDE = 16; // engine/panorama.py::VERTICES_PER_PANEL
const PANEL_FACE_STRIDE = 24; // engine/panorama.py::FACES_PER_PANEL
const FRAME_VERTEX_COUNT = 8;
const FRAME_FACE_COUNT = 12;
const CELL_SIZE_M = 0.156; // typical multicrystalline PV cell pitch — cosmetic tiling only

interface SplitPanelMeshes {
  frame: { vertices: Vec3[]; faces: number[][] };
  glass: { vertices: Vec3[]; faces: number[][]; uvs: [number, number][] };
}

/** Splits the merged `panels` mesh into a frame part and a glass part, and
 *  gives the glass part a real per-panel UV so a cell-grid texture tiles
 *  consistently across each module regardless of ITS OWN tilt/azimuth —
 *  computed per panel from that panel's own vertices (the largest-area
 *  glass triangle's normal, and an orthonormal basis around it), never
 *  from a single shared world-space projection that would skew on a
 *  rotated panel. Returns null if a mesh doesn't match the expected fixed
 *  layout (e.g. an older cached scene) so the caller can fall back safely
 *  instead of rendering garbage. */
function splitPanelMesh(mesh: SceneMeshDto): SplitPanelMeshes | null {
  const panelCount = mesh.vertices.length / PANEL_VERTEX_STRIDE;
  if (!Number.isInteger(panelCount) || panelCount <= 0) return null;
  if (mesh.faces.length !== panelCount * PANEL_FACE_STRIDE) return null;

  const frame: SplitPanelMeshes["frame"] = { vertices: [], faces: [] };
  const glass: SplitPanelMeshes["glass"] = { vertices: [], faces: [], uvs: [] };

  for (let i = 0; i < panelCount; i++) {
    const vStart = i * PANEL_VERTEX_STRIDE;
    const fStart = i * PANEL_FACE_STRIDE;

    const frameOffset = frame.vertices.length;
    for (let v = 0; v < FRAME_VERTEX_COUNT; v++) {
      frame.vertices.push(mesh.vertices[vStart + v] as Vec3);
    }
    for (let f = 0; f < FRAME_FACE_COUNT; f++) {
      const face = mesh.faces[fStart + f];
      frame.faces.push(face.map((idx) => idx - vStart + frameOffset));
    }

    const glassVerts: Vec3[] = [];
    for (let v = FRAME_VERTEX_COUNT; v < PANEL_VERTEX_STRIDE; v++) {
      glassVerts.push(mesh.vertices[vStart + v] as Vec3);
    }
    const glassFacesLocal: number[][] = [];
    let bestArea = -1;
    let bestNormal: Vec3 = [0, 0, 1];
    for (let f = FRAME_FACE_COUNT; f < PANEL_FACE_STRIDE; f++) {
      const face = mesh.faces[fStart + f].map((idx) => idx - vStart - FRAME_VERTEX_COUNT);
      glassFacesLocal.push(face);
      const [a, b, c] = face.map((idx) => glassVerts[idx]);
      const n = cross3(sub3(b, a), sub3(c, a));
      const area = len3(n);
      if (area > bestArea) {
        bestArea = area;
        bestNormal = area > 1e-9 ? norm3(n) : bestNormal;
      }
    }

    const centroidSum = glassVerts.reduce(
      (acc, p): Vec3 => [acc[0] + p[0], acc[1] + p[1], acc[2] + p[2]],
      [0, 0, 0] as Vec3
    );
    const centroid: Vec3 = [
      centroidSum[0] / glassVerts.length,
      centroidSum[1] / glassVerts.length,
      centroidSum[2] / glassVerts.length,
    ];

    const reference: Vec3 = Math.abs(bestNormal[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
    let u = norm3(cross3(reference, bestNormal));
    if (len3(u) < 1e-6) u = [1, 0, 0];
    const v = cross3(bestNormal, u);

    const glassOffset = glass.vertices.length;
    for (const p of glassVerts) {
      glass.vertices.push(p);
      const rel = sub3(p, centroid);
      glass.uvs.push([dot3(rel, u) / CELL_SIZE_M, dot3(rel, v) / CELL_SIZE_M]);
    }
    for (const face of glassFacesLocal) {
      glass.faces.push(face.map((idx) => idx + glassOffset));
    }
  }

  return { frame, glass };
}

function positionsGeometry(
  vertices: Vec3[],
  faces: number[][],
  uvs?: [number, number][]
): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(vertices.length * 3);
  vertices.forEach(([x, y, z], i) => {
    positions[i * 3] = x;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = z;
  });
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  if (uvs) {
    const uvArray = new Float32Array(uvs.length * 2);
    uvs.forEach(([u, v], i) => {
      uvArray[i * 2] = u;
      uvArray[i * 2 + 1] = v;
    });
    geometry.setAttribute("uv", new THREE.BufferAttribute(uvArray, 2));
  }
  geometry.setIndex(faces.flat());
  geometry.computeVertexNormals();
  return geometry;
}

/** A tileable PV-cell texture — a dark laminate square with a thin, low-
 *  contrast seam along its edges (the gap/busbar line between adjacent
 *  cells), repeated across each panel's own real per-panel UV from
 *  splitPanelMesh() above. Deliberately subtle: a surface detail, not a
 *  bold overlay grid. */
function usePanelCellTexture() {
  const [texture] = useState(() => {
    const size = 64;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    if (!ctx) return new THREE.Texture();

    ctx.fillStyle = "#0d1a33";
    ctx.fillRect(0, 0, size, size);
    ctx.strokeStyle = "rgba(130,150,190,0.35)";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(0.75, 0.75, size - 1.5, size - 1.5);

    const created = new THREE.CanvasTexture(canvas);
    created.wrapS = THREE.RepeatWrapping;
    created.wrapT = THREE.RepeatWrapping;
    created.colorSpace = THREE.SRGBColorSpace;
    return created;
  });
  return texture;
}

/** The real packed panel array, rendered as satin-aluminium frames (matte,
 *  slightly metallic) plus a glossy, cell-textured glass laminate (low
 *  roughness, thin clearcoat) — real geometry, real positions, real tilt/
 *  azimuth, split and shaded to read as individual modules instead of one
 *  flat-coloured slab. Falls back to the flat vertex-coloured mesh
 *  (previous behaviour) if the mesh doesn't match the expected per-panel
 *  layout. */
function PanelArray({ mesh }: { mesh: SceneMeshDto }) {
  const cellTexture = usePanelCellTexture();
  const split = useMemo(() => splitPanelMesh(mesh), [mesh]);
  const frameGeometry = useMemo(
    () => (split ? positionsGeometry(split.frame.vertices, split.frame.faces) : null),
    [split]
  );
  const glassGeometry = useMemo(
    () => (split ? positionsGeometry(split.glass.vertices, split.glass.faces, split.glass.uvs) : null),
    [split]
  );

  if (!split || !frameGeometry || !glassGeometry) {
    return <VertexColoredMesh mesh={mesh} fallbackColor="#1c2d64" />;
  }

  return (
    <group>
      <mesh geometry={frameGeometry} castShadow receiveShadow>
        <meshStandardMaterial color="#aab0bb" metalness={0.55} roughness={0.4} side={THREE.DoubleSide} />
      </mesh>
      <mesh geometry={glassGeometry} castShadow receiveShadow>
        <meshPhysicalMaterial
          map={cellTexture}
          roughness={0.16}
          metalness={0.05}
          clearcoat={0.85}
          clearcoatRoughness={0.08}
          envMapIntensity={1.4}
          side={THREE.DoubleSide}
        />
      </mesh>
    </group>
  );
}

/** Support-leg/rack geometry under flat-mounted panels
 *  (engine/panorama.py::_mounting_leg_mesh()) — a distinct galvanized-steel
 *  gray so it reads as hardware, not roof or panel. Purely presentation:
 *  the backend only emits this mesh, never repositions a panel because
 *  of it. */
function MountingStructure({ mesh }: { mesh: SceneMeshDto }) {
  return <VertexColoredMesh mesh={mesh} fallbackColor="#969498" />;
}

function ObstacleBoxes({ obstacles }: { obstacles: SceneObstacleDto[] }) {
  return (
    <>
      {obstacles.map((obstacle) => (
        <VertexColoredMesh key={obstacle.id} mesh={obstacle.mesh} fallbackColor="#c46a40" />
      ))}
    </>
  );
}

type CameraPreset = "iso" | "top" | "front" | "side";

interface Bounds3 {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  minZ: number;
  maxZ: number;
}

function boundsOf(vertices: number[][]): Bounds3 {
  const xs = vertices.map((v) => v[0]);
  const ys = vertices.map((v) => v[1]);
  const zs = vertices.map((v) => v[2]);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
    minZ: Math.min(...zs),
    maxZ: Math.max(...zs),
  };
}

/** Expands a horizontal (x/y) bounding box by `fraction` of its own width/
 *  depth on every side — a small margin so the framed subject isn't pressed
 *  right against the viewport edge, and enough roof/parapet shows around
 *  the panels for context. */
function padHorizontal(bounds: Bounds3, fraction: number): Bounds3 {
  const padX = (bounds.maxX - bounds.minX) * fraction;
  const padY = (bounds.maxY - bounds.minY) * fraction;
  return {
    ...bounds,
    minX: bounds.minX - padX,
    maxX: bounds.maxX + padX,
    minY: bounds.minY - padY,
    maxY: bounds.maxY + padY,
  };
}

/** Clamps a horizontal (x/y) bounding box inside another — keeps the
 *  padding above from ever framing wider than the real roof itself. */
function clampHorizontal(bounds: Bounds3, limit: Bounds3): Bounds3 {
  return {
    ...bounds,
    minX: Math.max(bounds.minX, limit.minX),
    maxX: Math.min(bounds.maxX, limit.maxX),
    minY: Math.max(bounds.minY, limit.minY),
    maxY: Math.min(bounds.maxY, limit.maxY),
  };
}

/** Center + radius the camera frames on. Fitted primarily to the real solar
 *  installation — panels, their mounting racks, and rooftop obstacles —
 *  rather than the full roof/building footprint: on an irregular, L-shaped
 *  or multi-plane roof the panels often only cover part of the merged roof
 *  mesh, and framing off the whole roof there leaves the actual array
 *  looking small and off-centre instead of being the main subject. A
 *  generous margin keeps some roof/parapet visible around the array for
 *  spatial context, clamped back to the roof's own footprint so it never
 *  frames wider than the real building. No panel layout yet (nothing to
 *  focus on) falls back to framing the whole roof, same as before. */
function useSceneBounds({
  roof,
  panels,
  mounting,
  obstacles,
}: {
  roof: SceneMeshDto;
  panels?: SceneMeshDto | null;
  mounting?: SceneMeshDto | null;
  obstacles?: SceneObstacleDto[];
}) {
  return useMemo(() => {
    const roofBounds = boundsOf(roof.vertices);

    const focusVertices: number[][] = [];
    if (panels && panels.vertices.length > 0) {
      focusVertices.push(...panels.vertices);
      if (mounting) focusVertices.push(...mounting.vertices);
      obstacles?.forEach((obstacle) => focusVertices.push(...obstacle.mesh.vertices));
    }
    const focusBounds = focusVertices.length > 0 ? boundsOf(focusVertices) : roofBounds;
    // A tighter margin than the roof-framing fallback below — enough for a
    // sliver of roof/parapet around the array for context, without the
    // installation itself reading as a small patch lost in empty roof.
    const framedBounds = clampHorizontal(padHorizontal(focusBounds, 0.22), roofBounds);

    const center: [number, number, number] = [
      (framedBounds.minX + framedBounds.maxX) / 2,
      (framedBounds.minY + framedBounds.maxY) / 2,
      (Math.min(roofBounds.minZ, focusBounds.minZ) + Math.max(roofBounds.maxZ, focusBounds.maxZ)) / 2,
    ];
    const radius = Math.max(
      (framedBounds.maxX - framedBounds.minX) / 2,
      (framedBounds.maxY - framedBounds.minY) / 2,
      3
    );

    if (process.env.NODE_ENV === "development") {
      console.debug("[Scene3DViewer] camera framing", {
        roofVertexCount: roof.vertices.length,
        panelVertexCount: panels?.vertices.length ?? 0,
        mountingVertexCount: mounting?.vertices.length ?? 0,
        obstacleCount: obstacles?.length ?? 0,
        roofBounds,
        focusBounds,
        framedBounds,
        center,
        radius,
      });
    }

    return { center, radius };
  }, [roof, panels, mounting, obstacles]);
}

function presetPosition(
  preset: CameraPreset,
  center: [number, number, number],
  radius: number
): [number, number, number] {
  const [cx, cy, cz] = center;
  const d = radius * 2.4;
  switch (preset) {
    case "top":
      return localToWorld([cx, cy, cz + d]);
    case "front": // camera to the south, looking north at the building's face
      return localToWorld([cx, cy - d, cz + radius * 0.5]);
    case "side": // camera to the east
      return localToWorld([cx + d, cy, cz + radius * 0.5]);
    case "iso":
    default:
      return localToWorld([cx + d * 0.55, cy - d * 0.55, cz + d * 0.55]);
  }
}

/** Eases the live camera/controls toward the selected preset on mount and on
 *  preset change, then gets out of the way. Two bugs lived here before:
 *
 *  1. The lerp ran every frame unconditionally, fighting any manual orbit
 *     drag — the camera kept getting pulled back toward the preset's fixed
 *     position forever, so it was never possible to orbit more than a few
 *     degrees off a preset.
 *  2. The fix for #1 ended the transition once `camera.position` got close
 *     to its target — but `<Canvas camera={{position: ...}}>` already sets
 *     the INITIAL camera position to that same value, so the check was
 *     satisfied on literally the first frame, before `controls.target`
 *     (which drei's OrbitControls starts at its own default of world
 *     origin, not the roof) had lerped anywhere close to the real target.
 *     The view froze aimed at world origin — near the base of the
 *     building — instead of the roof, and stayed that way forever since
 *     the transition had already (wrongly) ended.
 *
 *  Fixed by seeding OrbitControls' own initial `target` at the real
 *  world-space focus point (so there's no wrong-target frame at all), and
 *  by requiring BOTH camera position AND controls target to have converged
 *  before ending a transition — not position alone. */
function CameraRig({
  preset,
  center,
  radius,
}: {
  preset: CameraPreset;
  center: [number, number, number];
  radius: number;
}) {
  const controlsRef = useRef<OrbitControlsImpl>(null);
  const { camera } = useThree();
  const targetWorld = useMemo(() => localToWorld(center), [center]);
  const desiredPosition = useMemo(
    () => presetPosition(preset, center, radius),
    [preset, center, radius]
  );
  const transitioningRef = useRef(true);

  useEffect(() => {
    transitioningRef.current = true;
  }, [desiredPosition, targetWorld]);

  useFrame(() => {
    if (!transitioningRef.current) return;
    const controls = controlsRef.current;
    const positionGoal = new THREE.Vector3(...desiredPosition);
    const lookGoal = new THREE.Vector3(...targetWorld);
    const epsilon = Math.max(radius * 0.02, 0.05);

    camera.position.lerp(positionGoal, 0.08);
    let targetSettled = true;
    if (controls) {
      controls.target.lerp(lookGoal, 0.08);
      controls.update();
      targetSettled = controls.target.distanceTo(lookGoal) < epsilon;
    }

    // Close enough on BOTH position and look-at target — hand full control
    // back to OrbitControls instead of lerping indefinitely (a lerp
    // asymptotically approaches its target but never exactly reaches it).
    if (camera.position.distanceTo(positionGoal) < epsilon && targetSettled) {
      transitioningRef.current = false;
    }
  });

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      target={targetWorld}
      enableDamping
      dampingFactor={0.08}
      // Orbit/zoom for inspection only — panning would let the viewer drag
      // the building away from the camera's target, which reads as moving
      // the roof/panel geometry even though it doesn't actually touch it.
      enablePan={false}
      minDistance={radius * 0.6}
      maxDistance={radius * 6}
      // Keeps the camera between a slightly-above-horizon side view and a
      // steep-but-not-vertical downward angle — never a flat low side-on
      // shot or a pure top-down look straight down the roof normal. Applies
      // to vertical tilt only: horizontal orbit (azimuth) is unrestricted,
      // so the full 360 degrees around the roof is reachable.
      minPolarAngle={Math.PI * 0.12}
      maxPolarAngle={Math.PI * 0.47}
      // A manual drag ends the preset-easing immediately — otherwise the
      // still-running lerp keeps pulling the camera back toward the preset
      // position every frame, on top of the user's own drag.
      onStart={() => {
        transitioningRef.current = false;
      }}
    />
  );
}

const PRESETS: { key: CameraPreset; label: string }[] = [
  { key: "iso", label: "Isometric" },
  { key: "top", label: "Top" },
  { key: "front", label: "Front" },
  { key: "side", label: "Side" },
];

/** A mesh's own true footprint centre/radius — deliberately independent
 *  from useSceneBounds()'s camera-framing centre/radius. That one is
 *  tightened around the panel array on purpose (see useSceneBounds' own
 *  docstring), which is correct for framing the camera but is wrong for
 *  anything meant to scale/place itself against the REAL building's own
 *  size: fed into the wall texture's arc-length UV scale, it compressed
 *  the texture's UV span and rendered it visibly stretched/streaky on a
 *  building whose roof/walls are much larger than its panel array; fed
 *  into the decorative SiteContext's neighbour-building placement, it
 *  placed those neighbours close enough to sit on top of / overlap the
 *  real (larger) building instead of around it. Used for both, each
 *  against the mesh that actually represents the building's real size
 *  (walls, or roof when walls are missing). */
function useFootprintCenterRadius(mesh: SceneMeshDto | null): {
  center: [number, number, number];
  radius: number;
} {
  return useMemo(() => {
    if (!mesh || mesh.vertices.length === 0) return { center: [0, 0, 0] as [number, number, number], radius: 5 };
    const bounds = boundsOf(mesh.vertices);
    return {
      center: [
        (bounds.minX + bounds.maxX) / 2,
        (bounds.minY + bounds.maxY) / 2,
        (bounds.minZ + bounds.maxZ) / 2,
      ] as [number, number, number],
      radius: Math.max((bounds.maxX - bounds.minX) / 2, (bounds.maxY - bounds.minY) / 2, 1),
    };
  }, [mesh]);
}

export function Scene3DViewer({
  roof,
  walls,
  panels,
  mounting,
  obstacles,
}: {
  roof: SceneMeshDto;
  walls: SceneMeshDto | null;
  panels?: SceneMeshDto | null;
  mounting?: SceneMeshDto | null;
  obstacles?: SceneObstacleDto[];
}) {
  const [preset, setPreset] = useState<CameraPreset>("iso");
  const { center, radius } = useSceneBounds({ roof, panels, mounting, obstacles });
  // The real building's own footprint — walls when present (the true
  // outer envelope), the roof mesh otherwise — for anything that must
  // scale/place itself against how big the building actually is, as
  // opposed to `center`/`radius` above, which is deliberately tightened
  // around the panel array for camera framing.
  const buildingFootprint = useFootprintCenterRadius(walls ?? roof);
  const buildingWorldCenter = useMemo(
    () => localToWorld(buildingFootprint.center),
    [buildingFootprint.center]
  );
  const worldCenter = useMemo(() => localToWorld(center), [center]);

  return (
    <div className="relative h-[520px] w-full overflow-hidden rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)]">
      <div className="absolute right-3 top-3 z-10 flex gap-1 rounded-[var(--radius-app)] border border-line bg-paper/90 p-1 shadow-[var(--shadow-float)]">
        {PRESETS.map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => setPreset(p.key)}
            className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
              preset === p.key ? "bg-blue text-white" : "text-ink-soft hover:bg-surface-2"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      <Canvas
        shadows="soft"
        gl={{ toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.15 }}
        camera={{ position: presetPosition("iso", center, radius), fov: 45 }}
      >
        {/* Low, warm sun — golden-hour mood closer to the reviewed
            reference image (2026-09-10) than a flat midday overhead sun. */}
        <Sky sunPosition={[60, 22, 30]} turbidity={4} rayleigh={2.2} mieCoefficient={0.01} mieDirectionalG={0.85} />
        <SiteContext worldCenter={buildingWorldCenter} radius={buildingFootprint.radius} />

        {/* Real building — every vertex/face below is the backend's own
            geometry, unchanged. */}
        <group rotation={Z_UP_TO_Y_UP}>
          <RoofSurface mesh={roof} />
          {walls && (
            <TexturedBuildingMesh mesh={walls} center={buildingFootprint.center} radius={buildingFootprint.radius} />
          )}
          {panels && <PanelArray mesh={panels} />}
          {mounting && <MountingStructure mesh={mounting} />}
          {obstacles && obstacles.length > 0 && <ObstacleBoxes obstacles={obstacles} />}
        </group>

        <ambientLight intensity={0.45} color="#fff2df" />
        <directionalLight
          position={[worldCenter[0] + 55, 26, worldCenter[2] + 32]}
          intensity={1.6}
          color="#ffe9c7"
          castShadow
          shadow-mapSize={[2048, 2048]}
        />
        <Environment preset="sunset" />
        <CameraRig preset={preset} center={center} radius={radius} />
      </Canvas>
    </div>
  );
}
