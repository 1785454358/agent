import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { ShowcaseApp } from "./showcase/ShowcaseApp";
import "./styles/tokens.css";
import "./styles/app.css";

const queryClient = new QueryClient();
const showcase = import.meta.env.MODE === "showcase";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {showcase ? (
      <ShowcaseApp />
    ) : (
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    )}
  </StrictMode>,
);
