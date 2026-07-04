import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { UserProvider } from "./context/UserContext";
import { LanguageProvider } from "./i18n";
import "./index.css";

// Last-resort boundary: any uncaught render error shows a reload prompt rather
// than a blank page. Copy is fixed (English) since a crash here may predate the
// language context. Scoped, recoverable boundaries live closer to the features.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary
      fallback={() => (
        <div className="app-crash" role="alert">
          <h1>Something went wrong.</h1>
          <p>The page hit an unexpected error. Reloading usually fixes it.</p>
          <button
            className="btn btn-primary"
            onClick={() => window.location.reload()}
          >
            Reload
          </button>
        </div>
      )}
    >
      <LanguageProvider>
        <UserProvider>
          <App />
        </UserProvider>
      </LanguageProvider>
    </ErrorBoundary>
  </StrictMode>,
);
