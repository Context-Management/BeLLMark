// frontend/src/stores/benchmarkStore.ts
import { create } from 'zustand';

interface ProgressEvent {
  type: 'status' | 'generation' | 'judgment';
  timestamp: number;
  data: Record<string, unknown>;
}

interface BenchmarkStore {
  // Active run state
  activeRunId: number | null;
  phase: string;
  progress: number;
  events: ProgressEvent[];

  // Actions
  setActiveRun: (runId: number | null) => void;
  updateStatus: (phase: string, progress: number) => void;
  addEvent: (event: Omit<ProgressEvent, 'timestamp'>) => void;
  clearEvents: () => void;
}

export const useBenchmarkStore = create<BenchmarkStore>((set) => ({
  activeRunId: null,
  phase: 'idle',
  progress: 0,
  events: [],

  setActiveRun: (runId) => set({ activeRunId: runId, events: [], phase: 'idle', progress: 0 }),

  updateStatus: (phase, progress) => set({ phase, progress }),

  addEvent: (event) => set((state) => ({
    events: [...state.events, { ...event, timestamp: Date.now() }].slice(-100) // Keep last 100
  })),

  clearEvents: () => set({ events: [] }),
}));
