import type { Role } from "@/lib/session-token";

export type Operator = {
  id: string;
  password: string;
  role: Role;
  name: string;
};

export const OPERATORS: Operator[] = [
  { id: "analyst", password: "analyst-local", role: "analyst", name: "Analyst" },
  { id: "reviewer", password: "reviewer-local", role: "reviewer", name: "Reviewer" },
  { id: "admin", password: "admin-local", role: "admin", name: "Administrator" },
];

export function findOperator(id: string, password: string) {
  const operator = OPERATORS.find((item) => item.id === id);
  if (!operator || operator.password.length !== password.length) return null;
  let diff = 0;
  for (let index = 0; index < password.length; index += 1) {
    diff |= operator.password.charCodeAt(index) ^ password.charCodeAt(index);
  }
  return diff === 0 ? operator : null;
}

export function canReview(role: Role) {
  return role === "reviewer" || role === "admin";
}

export function canAdminister(role: Role) {
  return role === "admin";
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isUuid(value: string) {
  return UUID.test(value);
}
