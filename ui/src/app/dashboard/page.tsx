"use client";

import {
    ArrowDownRight,
    ArrowUpRight,
    Clock,
    PhoneCall,
    PhoneForwarded,
    Sparkles,
} from "lucide-react";
import {
    Area,
    AreaChart,
    Bar,
    BarChart,
    CartesianGrid,
    Cell,
    Legend,
    Line,
    LineChart,
    Pie,
    PieChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";

// SpinSci brand palette for charts
const BRAND = {
    purple: "#7759d9",
    violet: "#43226d",
    periwinkle: "#6486ff",
    green: "#04867c",
    mint: "#5ce0b0",
    sky: "#2ac6ff",
    slate: "#94a3b8",
};

// ---------------------------------------------------------------------------
// Sample analytics data. Shapes mirror what the platform captures for calls
// (call volume, dispositions, duration buckets, handle time). Replace with the
// live /organizations/reports + /usage endpoints to wire real data in.
// ---------------------------------------------------------------------------

const CALL_VOLUME = [
    { day: "Mon", inbound: 420, outbound: 180, transferred: 58 },
    { day: "Tue", inbound: 510, outbound: 210, transferred: 64 },
    { day: "Wed", inbound: 486, outbound: 240, transferred: 71 },
    { day: "Thu", inbound: 560, outbound: 260, transferred: 66 },
    { day: "Fri", inbound: 610, outbound: 300, transferred: 82 },
    { day: "Sat", inbound: 340, outbound: 120, transferred: 39 },
    { day: "Sun", inbound: 280, outbound: 90, transferred: 31 },
];

const DISPOSITIONS = [
    { disposition: "Resolved", count: 1840, fill: BRAND.mint },
    { disposition: "Scheduled", count: 960, fill: BRAND.periwinkle },
    { disposition: "Transferred", count: 411, fill: BRAND.purple },
    { disposition: "Voicemail", count: 236, fill: BRAND.sky },
    { disposition: "Callback", count: 188, fill: BRAND.violet },
    { disposition: "No Answer", count: 142, fill: BRAND.slate },
];

const DURATION_BUCKETS = [
    { bucket: "0-10s", count: 210 },
    { bucket: "10-30s", count: 640 },
    { bucket: "30-60s", count: 1180 },
    { bucket: "60-120s", count: 920 },
    { bucket: "120-180s", count: 460 },
    { bucket: ">180s", count: 267 },
];

const CONTAINMENT_TREND = [
    { week: "W1", rate: 71 },
    { week: "W2", rate: 74 },
    { week: "W3", rate: 78 },
    { week: "W4", rate: 82 },
    { week: "W5", rate: 85 },
    { week: "W6", rate: 88 },
];

const AGENT_BREAKDOWN = [
    { name: "Scheduling", value: 1420, fill: BRAND.purple },
    { name: "Billing", value: 980, fill: BRAND.periwinkle },
    { name: "Pharmacy", value: 760, fill: BRAND.mint },
    { name: "Referrals", value: 540, fill: BRAND.sky },
    { name: "Benefits", value: 317, fill: BRAND.violet },
];

const RECENT_CALLS = [
    { id: "9241", agent: "Scheduling", type: "Inbound", number: "+1 (415) 555-0148", disposition: "Scheduled", duration: "2m 14s" },
    { id: "9240", agent: "Billing", type: "Inbound", number: "+1 (312) 555-0199", disposition: "Resolved", duration: "1m 02s" },
    { id: "9239", agent: "Pharmacy", type: "Outbound", number: "+1 (206) 555-0132", disposition: "Callback", duration: "0m 46s" },
    { id: "9238", agent: "Referrals", type: "Inbound", number: "+1 (617) 555-0170", disposition: "Transferred", duration: "3m 51s" },
    { id: "9237", agent: "Scheduling", type: "Inbound", number: "+1 (713) 555-0121", disposition: "Resolved", duration: "1m 39s" },
];

const KPIS = [
    { label: "Total Calls", value: "5,140", delta: "+12.4%", up: true, icon: PhoneCall, sub: "vs. last week" },
    { label: "Avg Handle Time", value: "1m 48s", delta: "-8.0%", up: false, icon: Clock, sub: "30s faster than target" },
    { label: "Transfer Rate", value: "8.0%", delta: "-2.1%", up: false, icon: PhoneForwarded, sub: "411 calls transferred" },
    { label: "Resolution Rate", value: "88.2%", delta: "+5.6%", up: true, icon: Sparkles, sub: "resolved without a human" },
];

const DISPOSITION_BADGE: Record<string, string> = {
    Resolved: "bg-[#5ce0b0]/15 text-[#04867c] border-[#5ce0b0]/30",
    Scheduled: "bg-[#6486ff]/15 text-[#3a54c9] border-[#6486ff]/30",
    Transferred: "bg-[#7759d9]/15 text-[#5b3fc0] border-[#7759d9]/30",
    Callback: "bg-[#2ac6ff]/15 text-[#1487b5] border-[#2ac6ff]/30",
};

function ChartTooltip({
    active,
    payload,
    label,
}: {
    active?: boolean;
    payload?: Array<{ name?: string; value?: number | string; color?: string }>;
    label?: string | number;
}) {
    if (!active || !payload || payload.length === 0) return null;
    return (
        <div className="rounded-lg border bg-background p-3 shadow-lg">
            {label !== undefined && <p className="mb-1 text-sm font-semibold">{label}</p>}
            {payload.map((entry, i) => (
                <p key={i} className="text-sm" style={{ color: entry.color }}>
                    {entry.name ? `${entry.name}: ` : ""}
                    <span className="font-medium text-foreground">
                        {typeof entry.value === "number" ? entry.value.toLocaleString() : entry.value}
                    </span>
                </p>
            ))}
        </div>
    );
}

export default function DashboardPage() {
    return (
        <div className="container mx-auto space-y-6 p-6">
            {/* Header */}
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
                <div>
                    <h1 className="text-3xl font-bold">
                        Call{" "}
                        <span className="bg-gradient-to-r from-[#7759d9] to-[#2ac6ff] bg-clip-text text-transparent">
                            Analytics
                        </span>
                    </h1>
                    <p className="mt-1 text-muted-foreground">
                        A live pulse on patient access voice agents across your organization.
                    </p>
                </div>
                <Badge variant="outline" className="w-fit border-[#7759d9]/40 text-[#7759d9]">
                    Sample data · last 7 days
                </Badge>
            </div>

            {/* KPI cards */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {KPIS.map(({ label, value, delta, up, icon: Icon, sub }) => (
                    <Card key={label} className="overflow-hidden">
                        <div
                            className="h-1 w-full"
                            style={{ backgroundImage: "linear-gradient(90deg,#00e9aa,#6486ff 33%,#7759d9 66%,#43226d)" }}
                        />
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium text-muted-foreground">
                                {label}
                            </CardTitle>
                            <Icon className="h-4 w-4 text-[#7759d9]" />
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold">{value}</div>
                            <div className="mt-1 flex items-center gap-1 text-xs">
                                <span
                                    className={`inline-flex items-center gap-0.5 font-medium ${
                                        up ? "text-[#04867c]" : "text-[#c2410c]"
                                    }`}
                                >
                                    {up ? (
                                        <ArrowUpRight className="h-3 w-3" />
                                    ) : (
                                        <ArrowDownRight className="h-3 w-3" />
                                    )}
                                    {delta}
                                </span>
                                <span className="text-muted-foreground">{sub}</span>
                            </div>
                        </CardContent>
                    </Card>
                ))}
            </div>

            {/* Call volume + containment */}
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <Card className="lg:col-span-2">
                    <CardHeader>
                        <CardTitle>Call Volume</CardTitle>
                        <CardDescription>Inbound vs. outbound calls, with transfers</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <ResponsiveContainer width="100%" height={300}>
                            <AreaChart data={CALL_VOLUME} margin={{ top: 5, right: 12, left: 0, bottom: 0 }}>
                                <defs>
                                    <linearGradient id="inboundFill" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor={BRAND.purple} stopOpacity={0.5} />
                                        <stop offset="100%" stopColor={BRAND.purple} stopOpacity={0.02} />
                                    </linearGradient>
                                    <linearGradient id="outboundFill" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor={BRAND.mint} stopOpacity={0.5} />
                                        <stop offset="100%" stopColor={BRAND.mint} stopOpacity={0.02} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" opacity={0.12} />
                                <XAxis dataKey="day" tick={{ fontSize: 12 }} />
                                <YAxis tick={{ fontSize: 12 }} />
                                <Tooltip content={<ChartTooltip />} />
                                <Legend wrapperStyle={{ fontSize: 12 }} />
                                <Area
                                    type="monotone"
                                    dataKey="inbound"
                                    name="Inbound"
                                    stroke={BRAND.purple}
                                    strokeWidth={2}
                                    fill="url(#inboundFill)"
                                />
                                <Area
                                    type="monotone"
                                    dataKey="outbound"
                                    name="Outbound"
                                    stroke={BRAND.mint}
                                    strokeWidth={2}
                                    fill="url(#outboundFill)"
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle>Containment Rate</CardTitle>
                        <CardDescription>Resolved without a human handoff</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <ResponsiveContainer width="100%" height={300}>
                            <LineChart data={CONTAINMENT_TREND} margin={{ top: 5, right: 12, left: 0, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="3 3" opacity={0.12} />
                                <XAxis dataKey="week" tick={{ fontSize: 12 }} />
                                <YAxis domain={[60, 100]} tick={{ fontSize: 12 }} unit="%" />
                                <Tooltip content={<ChartTooltip />} />
                                <Line
                                    type="monotone"
                                    dataKey="rate"
                                    name="Containment"
                                    stroke={BRAND.periwinkle}
                                    strokeWidth={3}
                                    dot={{ r: 4, fill: BRAND.periwinkle }}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>
            </div>

            {/* Dispositions + duration + agent mix */}
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <Card>
                    <CardHeader>
                        <CardTitle>Disposition Distribution</CardTitle>
                        <CardDescription>Outcome of completed calls</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <ResponsiveContainer width="100%" height={280}>
                            <BarChart data={DISPOSITIONS} margin={{ top: 5, right: 12, left: 0, bottom: 40 }}>
                                <CartesianGrid strokeDasharray="3 3" opacity={0.12} />
                                <XAxis
                                    dataKey="disposition"
                                    angle={-40}
                                    textAnchor="end"
                                    height={60}
                                    interval={0}
                                    tick={{ fontSize: 11 }}
                                />
                                <YAxis tick={{ fontSize: 12 }} />
                                <Tooltip content={<ChartTooltip />} />
                                <Bar dataKey="count" name="Calls" radius={[4, 4, 0, 0]}>
                                    {DISPOSITIONS.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.fill} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle>Call Duration</CardTitle>
                        <CardDescription>Distribution across time buckets</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <ResponsiveContainer width="100%" height={280}>
                            <BarChart data={DURATION_BUCKETS} margin={{ top: 5, right: 12, left: 0, bottom: 20 }}>
                                <CartesianGrid strokeDasharray="3 3" opacity={0.12} />
                                <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
                                <YAxis tick={{ fontSize: 12 }} />
                                <Tooltip content={<ChartTooltip />} />
                                <Bar dataKey="count" name="Calls" radius={[4, 4, 0, 0]} fill={BRAND.periwinkle} />
                            </BarChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle>Calls by Agent</CardTitle>
                        <CardDescription>Share of volume per voice agent</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <ResponsiveContainer width="100%" height={280}>
                            <PieChart>
                                <Pie
                                    data={AGENT_BREAKDOWN}
                                    dataKey="value"
                                    nameKey="name"
                                    innerRadius={55}
                                    outerRadius={90}
                                    paddingAngle={2}
                                >
                                    {AGENT_BREAKDOWN.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.fill} />
                                    ))}
                                </Pie>
                                <Tooltip content={<ChartTooltip />} />
                                <Legend wrapperStyle={{ fontSize: 12 }} />
                            </PieChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>
            </div>

            {/* Recent calls */}
            <Card>
                <CardHeader>
                    <CardTitle>Recent Calls</CardTitle>
                    <CardDescription>Latest interactions handled by your voice agents</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b text-left text-muted-foreground">
                                    <th className="px-3 py-2 font-semibold">Run</th>
                                    <th className="px-3 py-2 font-semibold">Agent</th>
                                    <th className="px-3 py-2 font-semibold">Type</th>
                                    <th className="px-3 py-2 font-semibold">Phone Number</th>
                                    <th className="px-3 py-2 font-semibold">Disposition</th>
                                    <th className="px-3 py-2 text-right font-semibold">Duration</th>
                                </tr>
                            </thead>
                            <tbody>
                                {RECENT_CALLS.map((call) => (
                                    <tr key={call.id} className="border-b last:border-0 hover:bg-muted/40">
                                        <td className="px-3 py-2 font-mono">#{call.id}</td>
                                        <td className="px-3 py-2">{call.agent}</td>
                                        <td className="px-3 py-2">{call.type}</td>
                                        <td className="px-3 py-2">{call.number}</td>
                                        <td className="px-3 py-2">
                                            <span
                                                className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${
                                                    DISPOSITION_BADGE[call.disposition] ??
                                                    "border-border bg-muted text-muted-foreground"
                                                }`}
                                            >
                                                {call.disposition}
                                            </span>
                                        </td>
                                        <td className="px-3 py-2 text-right">{call.duration}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
