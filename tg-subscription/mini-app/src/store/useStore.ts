import { create } from "zustand";
import { api, Plan, Subscription } from "../api/client";

interface Store {
  plans: Plan[];
  subscription: Subscription | null;
  loading: boolean;
  fetchPlans: () => Promise<void>;
  fetchSubscription: () => Promise<void>;
}

export const useStore = create<Store>((set) => ({
  plans: [],
  subscription: null,
  loading: false,

  fetchPlans: async () => {
    set({ loading: true });
    const res = await api.getPlans();
    set({ plans: res.data, loading: false });
  },

  fetchSubscription: async () => {
    const res = await api.getCurrentSubscription();
    set({ subscription: res.data });
  },
}));
