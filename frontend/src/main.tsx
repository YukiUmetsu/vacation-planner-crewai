import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { CallbackPage } from "./auth/CallbackPage";
import { MetricsPage } from "./pages/MetricsPage";
import "./index.css";

const queryClient = new QueryClient();

function Root() {
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  // Match infra cognito callback_urls default: http://localhost:5173/callback
  if (path === "/callback") {
    return <CallbackPage />;
  }
  if (path === "/metrics") {
    return <MetricsPage />;
  }
  return <App />;
}

createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={queryClient}>
    <StrictMode>
      <Root />
    </StrictMode>
  </QueryClientProvider>,
);
