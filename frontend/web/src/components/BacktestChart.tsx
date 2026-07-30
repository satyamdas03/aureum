import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import type { Certificate } from "../types";

export default function BacktestChart({
  certificate,
}: {
  certificate: Certificate | null;
}) {
  const data = certificate?.execution_trace?.daily_nav || [];

  if (!data.length) {
    return (
      <div className="h-48 flex items-center justify-center text-slate font-mono-data text-mono-data">
        Run a backtest to see the NAV curve.
      </div>
    );
  }

  const initial = data[0]?.nav ?? 1;

  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <defs>
            <linearGradient id="navGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#C9A227" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#C9A227" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1A2233" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: "#8A91A8", fontSize: 10 }}
            tickFormatter={(date: string) => date.slice(0, 7)}
            minTickGap={30}
            axisLine={{ stroke: "#1A2233" }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#8A91A8", fontSize: 10 }}
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
            axisLine={{ stroke: "#1A2233" }}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#111827",
              border: "1px solid #1A2233",
              borderRadius: "4px",
              color: "#F5F1E8",
            }}
            formatter={(value: number) => [
              `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
              "NAV",
            ]}
            labelFormatter={(label: string) => label}
          />
          <Area
            type="monotone"
            dataKey="nav"
            stroke="#C9A227"
            strokeWidth={2}
            fill="url(#navGradient)"
            baseValue={initial}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
