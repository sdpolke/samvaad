"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";

interface CallbackRequest {
    id: number;
    lead_name: string | null;
    phone_number: string;
    company: string | null;
    callback_date: string;
    callback_time: string;
    timezone: string;
    reason: string | null;
    status: string;
    created_at: string;
}

function StatusBadge({ status }: { status: string }) {
    const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
        pending: "default",
        completed: "secondary",
        cancelled: "outline",
        failed: "destructive",
    };
    return <Badge variant={variants[status] || "default"}>{status}</Badge>;
}

export default function CampaignCallbacksPage() {
    const params = useParams();
    const campaignId = params.campaignId as string;
    const [callbacks, setCallbacks] = useState<CallbackRequest[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchCallbacks = async () => {
        try {
            const res = await fetch(`/api/v1/callbacks/campaign/${campaignId}`);
            if (res.ok) {
                const data = await res.json();
                setCallbacks(data.callbacks || []);
            }
        } catch (err) {
            console.error("Failed to fetch callbacks:", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchCallbacks();
    }, [campaignId]);

    const cancelCallback = async (callbackId: number) => {
        try {
            const res = await fetch(`/api/v1/callbacks/${callbackId}/cancel`, {
                method: "POST",
            });
            if (res.ok) {
                toast.success("Callback cancelled");
                fetchCallbacks();
            } else {
                toast.error("Failed to cancel callback");
            }
        } catch {
            toast.error("Failed to cancel callback");
        }
    };

    if (loading) {
        return <div className="p-6">Loading callbacks...</div>;
    }

    return (
        <div className="p-6">
            <Card>
                <CardHeader>
                    <CardTitle>Scheduled Callbacks</CardTitle>
                    <CardDescription>
                        Follow-up calls scheduled by the voice agent during conversations.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {callbacks.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No callbacks scheduled for this campaign.</p>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Lead</TableHead>
                                    <TableHead>Phone</TableHead>
                                    <TableHead>Scheduled</TableHead>
                                    <TableHead>Timezone</TableHead>
                                    <TableHead>Reason</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead>Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {callbacks.map((cb) => (
                                    <TableRow key={cb.id}>
                                        <TableCell>{cb.lead_name || "—"}</TableCell>
                                        <TableCell className="font-mono text-xs">{cb.phone_number}</TableCell>
                                        <TableCell>{cb.callback_date} {cb.callback_time}</TableCell>
                                        <TableCell>{cb.timezone}</TableCell>
                                        <TableCell className="max-w-[200px] truncate">{cb.reason || "—"}</TableCell>
                                        <TableCell><StatusBadge status={cb.status} /></TableCell>
                                        <TableCell>
                                            {cb.status === "pending" && (
                                                <Button
                                                    variant="destructive"
                                                    size="sm"
                                                    onClick={() => cancelCallback(cb.id)}
                                                >
                                                    Cancel
                                                </Button>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
