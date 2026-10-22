// Testing Library's DOM matchers (`toBeInTheDocument`, …) on Vitest's expect,
// and a clean DOM between tests.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());
