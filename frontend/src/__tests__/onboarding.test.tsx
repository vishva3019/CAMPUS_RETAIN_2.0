import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { composeEmail, domainMessage, emailError, initials, localPart, nameError, passwordStrength, studentIdError, type OnboardCollege } from "../onboarding/lib";
import { OtpInput } from "../onboarding/parts";
import { useState } from "react";

const college = (name: string, domain: string): OnboardCollege => ({
  id: 1, slug: "x", name, short_name: null, city: null, logo_url: null, primary_color: "#123456", domains: [domain],
});
const alliance = college("Alliance University", "ced.alliance.edu.in");
const mvj = college("MVJ College of Engineering", "mvjce.edu.in");
const vemana = college("Vemana Institute of Technology", "vemanait.edu.in");

describe("college email rules", () => {
  it("accepts each college's own domain", () => {
    expect(emailError("madhusudhan@ced.alliance.edu.in", alliance)).toBeNull();
    expect(emailError("student@mvjce.edu.in", mvj)).toBeNull();
    expect(emailError("Student@VemanaIT.edu.in ", vemana)).toBeNull();
  });
  it("rejects gmail and other colleges' domains with the college's message", () => {
    expect(emailError("student@gmail.com", alliance)).toBe(domainMessage(alliance));
    expect(emailError("student@mvjce.edu.in", alliance)).toBe("Please enter your official Alliance University email address ending with @ced.alliance.edu.in.");
    expect(emailError("student@ced.alliance.edu.in", mvj)).toBe(domainMessage(mvj));
    expect(emailError("student@vemanait.edu.in", alliance)).toBe(domainMessage(alliance));
    expect(emailError("x@cse.vemanait.edu.in", vemana)).toBe(domainMessage(vemana));
  });
  it("rejects malformed addresses", () => {
    expect(emailError("", alliance)).toMatch(/Enter your college email/);
    expect(emailError("a b@ced.alliance.edu.in", alliance)).toMatch(/valid email/);
    expect(emailError("a@@ced.alliance.edu.in", alliance)).toMatch(/valid email/);
  });
  it("builds the address from the part typed before the fixed domain", () => {
    expect(composeEmail(" Asha.Rao ", "ced.alliance.edu.in")).toBe("asha.rao@ced.alliance.edu.in");
    expect(localPart("asha@ced.alliance.edu.in", alliance)).toBe("asha");
    expect(localPart("asha@gmail.com", alliance)).toBe("asha@gmail.com");      // kept, so the error shows
  });
});

describe("form checks", () => {
  it("validates names and student IDs", () => {
    expect(nameError("Asha Rao")).toBeNull();
    expect(nameError("R. K. Sharma")).toBeNull();
    expect(nameError("A")).not.toBeNull();
    expect(nameError("<b>x</b>")).not.toBeNull();
    expect(studentIdError("1mj22cs001")).toBeNull();
    expect(studentIdError("!!")).not.toBeNull();
  });
  it("scores password strength", () => {
    expect(passwordStrength("short").score).toBe(0);
    expect(passwordStrength("password123").score).toBeLessThanOrEqual(1);
    expect(passwordStrength("Blue-Kettle-Orbit-73").label).toBe("Strong");
    expect(passwordStrength("ashwini2026x", 8, ["ashwini"]).score).toBeLessThanOrEqual(1);
  });
  it("makes placeholder monograms from the college name", () => {
    expect(initials("Alliance University")).toBe("AU");
    expect(initials("MVJ College of Engineering")).toBe("MCE");
    expect(initials("Vemana Institute of Technology")).toBe("VIT");
  });
});

function Harness({ onComplete }: { onComplete: (v: string) => void }) {
  const [v, setV] = useState("");
  return <OtpInput value={v} onChange={setV} onComplete={onComplete} label="Code" />;
}

describe("OtpInput", () => {
  it("moves focus as you type and submits at 6 digits", async () => {
    const done = vi.fn();
    render(<Harness onComplete={done} />);
    const boxes = screen.getAllByRole("textbox");
    expect(boxes).toHaveLength(6);
    await userEvent.click(boxes[0]);
    await userEvent.keyboard("12a3456");
    expect(boxes.map((b) => (b as HTMLInputElement).value).join("")).toBe("123456");
    expect(done).toHaveBeenCalledWith("123456");
  });
  it("accepts a pasted code and supports backspace", async () => {
    const done = vi.fn();
    render(<Harness onComplete={done} />);
    const boxes = screen.getAllByRole("textbox");
    await userEvent.click(boxes[0]);
    await userEvent.paste("Code: 654 321");
    expect(done).toHaveBeenCalledWith("654321");
    await userEvent.keyboard("{Backspace}");
    expect(boxes.map((b) => (b as HTMLInputElement).value).join("")).toBe("65432");
  });
});

import { firstName } from "../components/WelcomeSplash";
import type { Session } from "../lib/types";

describe("welcome greeting name", () => {
  const s = (full_name: string | null, email: string) => ({ user: { full_name, email } } as unknown as Session);
  it("uses the first name, else a tidy part of the email", () => {
    expect(firstName(s("Madhusudhan Rao", "madhu@ced.alliance.edu.in"))).toBe("Madhusudhan");
    expect(firstName(s(null, "madhu.rao@ced.alliance.edu.in"))).toBe("Madhu");
    expect(firstName(s("", "ravi_kumar21@mvjce.edu.in"))).toBe("Ravi");
  });
});
