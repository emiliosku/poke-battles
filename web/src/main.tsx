import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth";
import "./styles.css";

const basename = (import.meta.env.BASE_URL || "/").replace(/\/$/, "") || "/";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter basename={basename}>
        <App />
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>
);
