// Catches render-time exceptions in its subtree so a single malformed payload
// (e.g. a scan response from a backend whose shape has drifted from the UI's
// types) degrades to a recoverable message instead of white-screening the whole
// app. React error boundaries must be class components — there is no hook form.
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  // Rendered in place of the crashed subtree. `reset` clears the caught error so
  // the children re-mount (pair with `resetKeys` or a user action that changes
  // the input, or the same error will recur immediately).
  fallback: (error: Error, reset: () => void) => ReactNode;
  // When any entry changes (shallow compare), a caught error is cleared so a new
  // attempt can render — e.g. a fresh scan result replacing a broken one.
  resetKeys?: unknown[];
}

interface State {
  error: Error | null;
}

function keysChanged(a: unknown[] = [], b: unknown[] = []): boolean {
  if (a.length !== b.length) return true;
  return a.some((v, i) => !Object.is(v, b[i]));
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && keysChanged(prev.resetKeys, this.props.resetKeys)) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep the real stack in the console; the UI only shows the friendly copy.
    console.error("Render error caught by ErrorBoundary:", error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return this.props.fallback(this.state.error, this.reset);
    }
    return this.props.children;
  }
}
