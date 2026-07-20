"use client";

import { ArrowRight, BarChart3, CalendarCheck, Headset, Phone, Pill, Receipt } from 'lucide-react';
import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/lib/auth';

const VOICE_AGENTS = [
    { icon: CalendarCheck, title: 'Scheduling', copy: 'Books, reschedules, and cancels appointments across providers and locations.' },
    { icon: Pill, title: 'Pharmacy', copy: 'Handles medication questions, refill requests, and pharmacy coordination.' },
    { icon: Receipt, title: 'Billing', copy: 'Answers billing inquiries, payment questions, and balance resolution.' },
    { icon: Headset, title: 'Referrals', copy: 'Captures referral requests and routes patients to the right provider.' },
];

export default function OverviewPage() {
    const { user, provider } = useAuth();
    const isOSSMode = provider !== 'stack';
    const firstName = user?.displayName ? user.displayName.split(' ')[0] : '';

    return (
        <div className="container mx-auto px-4 py-8">
            <div className="mx-auto max-w-5xl space-y-8">
                {/* Gradient hero */}
                <section className="spinsci-hero relative overflow-hidden rounded-2xl px-8 py-12 text-white shadow-sm sm:px-12">
                    <span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-white/80">
                        <Phone className="h-3.5 w-3.5" />
                        Voice AI for Patient Access
                    </span>

                    <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl">
                        {isOSSMode ? (
                            <>The faster, smarter way to run <span className="bg-gradient-to-r from-[#00e9aa] via-[#6486ff] to-[#c9b6ff] bg-clip-text text-transparent">patient access</span></>
                        ) : (
                            <>Welcome back{firstName ? `, ${firstName}` : ''}. Let&apos;s move <span className="bg-gradient-to-r from-[#00e9aa] via-[#6486ff] to-[#c9b6ff] bg-clip-text text-transparent">patient access</span> forward</>
                        )}
                    </h1>

                    {/* Voice AI paragraph (adapted from spinsci.ai/solutions/voice-ai) */}
                    <p className="mt-5 max-w-3xl text-base leading-relaxed text-white/75 sm:text-lg">
                        Under pressure to serve more patients while reducing administrative burden, health
                        systems need a modern approach to patient access. SpinSci delivers a human-like voice AI
                        experience from first contact to final bill. AI agents resolve scheduling, prescription,
                        billing, and referral requests accurately, at any volume, around the clock, while your
                        team focuses on the complex cases that need a human touch. When higher-touch support is
                        needed, the handoff is instant and complete, with full conversation context passed to a
                        live agent before the first word is spoken.
                    </p>

                    <div className="mt-7 flex flex-wrap gap-3">
                        <Button asChild size="lg" className="bg-white text-[#122643] hover:bg-white/90">
                            <Link href="/workflow">
                                Build a Voice Agent
                                <ArrowRight className="ml-1 h-4 w-4" />
                            </Link>
                        </Button>
                        <Button asChild size="lg" variant="outline" className="border-white/30 bg-transparent text-white hover:bg-white/10 hover:text-white">
                            <Link href="/dashboard">
                                View Call Analytics
                            </Link>
                        </Button>
                    </div>

                    <div className="spinsci-gradient-rule mt-10 h-px w-full opacity-70" />

                    {/* Voice agent capabilities */}
                    <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                        {VOICE_AGENTS.map(({ icon: Icon, title, copy }) => (
                            <div key={title} className="rounded-xl border border-white/10 bg-white/5 p-4 backdrop-blur-sm">
                                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10">
                                    <Icon className="h-4 w-4 text-[#5ce0b0]" />
                                </div>
                                <p className="mt-3 text-sm font-semibold text-white">{title}</p>
                                <p className="mt-1 text-xs leading-relaxed text-white/60">{copy}</p>
                            </div>
                        ))}
                    </div>
                </section>

                {/* Quick actions */}
                <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
                    <Card className="border-t-2 border-t-[#7759d9]">
                        <CardHeader>
                            <CardTitle>Voice Agents</CardTitle>
                            <CardDescription>
                                Build powerful AI voice agents with the visual editor.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Button asChild>
                                <Link href="/workflow">Go to Agents</Link>
                            </Button>
                        </CardContent>
                    </Card>

                    <Card className="border-t-2 border-t-[#04867c]">
                        <CardHeader>
                            <CardTitle>Call Analytics</CardTitle>
                            <CardDescription>
                                Track call volume, dispositions, transfers, and duration trends.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Button asChild variant="outline">
                                <Link href="/dashboard">
                                    <BarChart3 className="mr-1 h-4 w-4" />
                                    Open Dashboard
                                </Link>
                            </Button>
                        </CardContent>
                    </Card>

                    <Card className="border-t-2 border-t-[#6486ff]">
                        <CardHeader>
                            <CardTitle>Configure Services</CardTitle>
                            <CardDescription>
                                Set up your AI services like LLM, TTS, and STT providers.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Button asChild variant="outline">
                                <Link href="/model-configurations">Configure Models</Link>
                            </Button>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}
