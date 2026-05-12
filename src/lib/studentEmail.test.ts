import { describe, expect, it } from "vitest";
import { isStudentOrAcademicEmail } from "./studentEmail";

describe("isStudentOrAcademicEmail", () => {
  it("returns false for empty or non-academic", () => {
    expect(isStudentOrAcademicEmail("")).toBe(false);
    expect(isStudentOrAcademicEmail(null)).toBe(false);
    expect(isStudentOrAcademicEmail("user@gmail.com")).toBe(false);
    expect(isStudentOrAcademicEmail("bad")).toBe(false);
  });

  it("detects common academic TLD patterns", () => {
    expect(isStudentOrAcademicEmail("a@mit.edu")).toBe(true);
    expect(isStudentOrAcademicEmail("a@university.edu.cn")).toBe(true);
    expect(isStudentOrAcademicEmail("a@soton.ac.uk")).toBe(true);
    expect(isStudentOrAcademicEmail("a@tokyo.ac.jp")).toBe(true);
  });
});
