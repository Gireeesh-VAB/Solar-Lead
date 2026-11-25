// A deliberately tiny, dependency-free horizontal bar chart — inline SVG +
// tokens only, matching this app's "don't add a dependency for something
// SVG/CSS already does" discipline (see the processing page's StageAnimation).
// It only ever renders numbers the caller already has on screen; it never
// fetches anything of its own.

export type MiniBarDatum = {
  label: string;
  value: number;
  /** A CSS color — pass a design token, e.g. "var(--good)". */
  color: string;
};

const ROW_H = 24;
const BAR_H = 10;
const LABEL_W = 116;
const VALUE_W = 34;
const WIDTH = 320;

export function MiniBarChart({
  data,
  title,
  valueSuffix = "",
}: {
  data: MiniBarDatum[];
  /** Accessible name for the chart; the visible heading lives with the caller. */
  title: string;
  valueSuffix?: string;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  const trackX = LABEL_W;
  const trackW = WIDTH - LABEL_W - VALUE_W - 8;
  const height = data.length * ROW_H;

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${height}`}
      width="100%"
      height={height}
      role="img"
      aria-label={`${title}: ${data.map((d) => `${d.label} ${d.value}${valueSuffix}`).join(", ")}`}
      className="overflow-visible"
    >
      {data.map((d, i) => {
        const y = i * ROW_H;
        const barY = y + (ROW_H - BAR_H) / 2;
        // Every bar is direct-labelled with its name and value, so the
        // status hues are never the only thing carrying identity.
        const w = Math.max(d.value > 0 ? 3 : 0, (d.value / max) * trackW);
        return (
          <g key={d.label}>
            <text
              x={0}
              y={y + ROW_H / 2}
              dominantBaseline="middle"
              fontSize={11}
              fill="var(--ink-soft)"
            >
              {d.label}
            </text>
            <rect
              x={trackX}
              y={barY}
              width={trackW}
              height={BAR_H}
              rx={4}
              fill="var(--surface-2)"
            />
            {w > 0 && (
              <rect x={trackX} y={barY} width={w} height={BAR_H} rx={4} fill={d.color}>
                <title>{`${d.label}: ${d.value}${valueSuffix}`}</title>
              </rect>
            )}
            <text
              x={WIDTH}
              y={y + ROW_H / 2}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={11}
              fill="var(--ink)"
              className="font-mono tabular"
            >
              {d.value}
              {valueSuffix}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
