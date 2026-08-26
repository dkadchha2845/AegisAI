import React from "react";
import { createRoot } from "react-dom/client";
import App from "@/App";
import { applyStoredMotionPreference } from "@/hooks/useMotionPreference";

// Before React mounts, so the very first paint already obeys a stored choice
// rather than animating once and then stopping.
applyStoredMotionPreference();

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
