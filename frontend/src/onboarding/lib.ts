/** Shared types and checks for the onboarding and sign-in screens. The server repeats every
 * check (the college's domains come from its database record); these give instant feedback. */
import { api, setCsrfToken } from "../lib/api";

export interface OnboardCollege {
  id: number;
  slug: string;
  name: string;
  short_name: string | null;
  city: string | null;
  logo_url: string | null;
  primary_color: string;
  domains: string[];
}

export interface Bootstrap {
  csrf_token: string;
  signed_in: boolean;
  home: string | null;
  colleges: OnboardCollege[];
  years: { value: string; label: string }[];
  password_min: number;
  code: { length: number; ttl_minutes: number; resend_seconds: number; max_attempts: number };
  remember_days: number;
}

export interface CodeSent {
  status: "code_sent";
  email: string;
  purpose: "signup" | "verify" | "reset";
  resend_in: number;
  expires_in: number;
}

export interface SignedIn {
  status: "signed_in";
  home: string;
  user: { full_name: string | null; email: string };
  college: { name: string; display_name: string } | null;
}

export async function loadBootstrap(): Promise<Bootstrap> {
  const data = await api.get<Bootstrap>("/api/v1/auth/bootstrap");
  setCsrfToken(data.csrf_token);
  return data;
}

export function normalizeEmail(raw: string) {
  return raw.normalize("NFKC").trim().toLowerCase();
}

export function domainMessage(college: OnboardCollege) {
  const ending = college.domains.map((d) => `@${d}`).join(" or ");
  return `Please enter your official ${college.name} email address ending with ${ending}.`;
}

const LOCAL_RE = /^[a-z0-9](?:[a-z0-9._%+-]{0,62}[a-z0-9_%+-])?$/;

/** Build the full address from what was typed in the box in front of the fixed "@domain". */
export function composeEmail(typed: string, domain: string) {
  const value = normalizeEmail(typed);
  return value.includes("@") ? value : `${value}@${domain}`;
}

/** null when the address is valid for this college, else the message to show. */
export function emailError(email: string, college: OnboardCollege): string | null {
  const value = normalizeEmail(email);
  if (!value || value.startsWith("@")) return "Enter your college email address.";
  const at = value.split("@");
  if (at.length !== 2 || !LOCAL_RE.test(at[0]) || at[0].includes("..") || /\s/.test(value)) return "Enter a valid email address.";
  if (!college.domains.map((d) => d.toLowerCase()).includes(at[1])) return domainMessage(college);
  return null;
}

/** What the student typed before the "@", so pasting a full address still works. */
export function localPart(typed: string, college: OnboardCollege) {
  const value = normalizeEmail(typed);
  const [local, domain] = value.split("@");
  return domain !== undefined && college.domains.includes(domain) ? local : value;
}

export function nameError(name: string) {
  const v = name.trim().replace(/\s+/g, " ");
  if (v.length < 2) return "Enter your full name.";
  if (!/^[\p{L}]+(?:[ .'-][\p{L}]*)*$/u.test(v)) return "Use letters only in your name (spaces, dots, hyphens and apostrophes are fine).";
  return null;
}

export function studentIdError(sid: string) {
  const v = sid.replace(/\s+/g, "").toUpperCase();
  return /^[A-Z0-9][A-Z0-9/-]{2,29}$/.test(v) ? null : "Enter your student ID or USN as printed on your ID card (letters and numbers).";
}

export interface Strength {
  score: 0 | 1 | 2 | 3 | 4;
  label: string;
  tips: string[];
}

const COMMON = ["password", "12345678", "qwerty", "iloveyou", "letmein", "welcome", "admin", "campusretain", "college", "student"];

export function passwordStrength(pw: string, min = 8, avoid: string[] = []): Strength {
  if (!pw) return { score: 0, label: "", tips: [] };
  const tips: string[] = [];
  let points = 0;
  if (pw.length >= min) points++;
  else tips.push(`Use at least ${min} characters`);
  if (pw.length >= 12) points++;
  else if (pw.length >= min) tips.push("12 or more characters is stronger");
  const classes = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/].filter((r) => r.test(pw)).length;
  if (classes >= 3) points++;
  else tips.push("Mix upper and lower case, numbers or symbols");
  if (classes === 4 || pw.length >= 16) points++;
  const lower = pw.toLowerCase();
  const weak = COMMON.some((c) => lower.includes(c)) || new Set(pw).size < 4 ||
    avoid.some((a) => a.length >= 4 && lower.includes(a.toLowerCase()));
  if (weak) {
    tips.unshift("Avoid common words, your email and your USN");
    points = Math.min(points, 1);
  }
  if (pw.length < min) points = 0;
  const score = Math.max(points, pw.length >= min ? 1 : 0) as Strength["score"];
  return { score, label: ["Too short", "Weak", "Fair", "Good", "Strong"][score], tips };
}

export function initials(name: string) {
  const words = name.replace(/[^\p{L}\s]/gu, " ").split(/\s+/).filter((w) => w && !["of", "and", "the"].includes(w.toLowerCase()));
  return (words.slice(0, 3).map((w) => w[0]).join("") || "?").toUpperCase();
}

export function mmss(seconds: number) {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
