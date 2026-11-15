export type Kind = "found" | "lost";
export type ItemStatus = "Available" | "Pending" | "Claimed" | "Returned" | "Removed";
export type ClaimStatus = "pending" | "approved" | "rejected" | "withdrawn" | "collected" | "closed";

export interface Session {
  user: {
    id: number; email: string; full_name: string | null; role: string; role_label: string;
    campus: string | null; permissions: string[]; student_id?: string | null;
  };
  college: null | {
    id: number; slug: string; name: string; display_name: string; primary_color: string | null;
    support_office: string | null; contact_email: string | null; campuses: { id: number; name: string }[];
    network?: boolean;
    plan?: { key: string; label: string; features: string[]; limits: Record<string, number | null>; note: string | null; period_end: string | null; status: string | null };
  };
  csrf_token: string;
  config: { max_photos: number; max_image_mb: number; categories: string[]; pickup_code_max_attempts: number; ai_enabled?: boolean };
  unread: number;
  greet?: boolean;
}

export interface CollectionPoint {
  id: number; name: string; opening_hours: string | null; description: string | null;
  campus: string | null; is_active: boolean; pickup_text: string; items_held?: number;
}

export interface StaffClaim {
  id: number; status: ClaimStatus; timestamp: string;
  student_id?: string | null; student_email?: string | null; phone?: string | null;
  proof_description?: string | null; reviewed_by?: string | null; reviewed_at?: string | null;
  review_remarks?: string | null; collected_at?: string | null; collected_by?: string | null;
  flags?: { code: string; message: string }[];
}

export interface Match {
  id: number; score: number; status: string; reasons: { name_similarity?: number; place_similarity?: number; same_category?: boolean; days_apart?: number };
  ai_verdict: string | null; ai_reason: string | null; ai_checked_at: string | null; item: Item;
  lost_item_id?: number; lost_item_name?: string;
}

export interface Item {
  id: number; ref: string; kind: Kind; name: string; category: string | null; location: string | null;
  description: string | null; occurred_on: string | null; reported_at: string | null;
  status: ItemStatus; photos: string[]; is_mine: boolean; campus: string | null;
  collection_point: CollectionPoint | null; can_claim: boolean; can_report_found: boolean;
  event?: { id: number; name: string } | null; has_location?: boolean;
  my_claim?: { id: number; status: ClaimStatus; timestamp: string } | null; // item detail only
  score?: number;
  // staff only
  reported_by?: string | null; secret_detail?: string | null; claims?: StaffClaim[]; removed_at?: string | null;
}

export interface Page<T> { items: T[]; page: number; pages: number; total: number; per_page: number }

export type ClaimStage = "under_review" | "awaiting_pickup" | "returned" | "rejected" | "withdrawn" | "closed";

export interface MyClaim {
  id: number; status: ClaimStatus; stage: ClaimStage; stage_label: string; timestamp: string; reviewed_at: string | null;
  review_remarks: string | null; collected_at: string | null;
  finder?: Finder | null;
  item: { id: number; ref: string; name: string; category: string | null; location: string | null; photo: string | null; college: string | null };
  pickup: null | { instructions: string; point: CollectionPoint | null; code_sent_at: string | null; code_expires_at: string | null; locked: boolean };
}

export interface ReviewClaim extends StaffClaim {
  claimant_college: string | null;
  item: Item;
  claimant_history: Partial<Record<ClaimStatus, number>>;
}

export interface Notification {
  id: number; kind: string; title: string; body: string | null; link: string | null; created_at: string; read: boolean;
}

export interface DeskClaim {
  id: number; student_email: string; student_id: string | null; phone: string | null;
  reviewed_at: string | null; wrong_attempts: number; has_code: boolean;
  collected_at: string | null; collected_by: string | null;
  item: { id: number; name: string; photo: string | null; collection_point: string | null };
}

export interface College {
  id: number; slug: string; name: string; short_name: string | null; city: string | null; status: string;
  domains: string[]; created_at: string; contact_email: string | null; support_office: string | null;
  accounts: number; items: number; approved_or_returned: number; admins: { email: string; invited: boolean }[];
  listed_on_signup: boolean;
}

export interface CollegeEvent {
  id: number; slug: string; name: string; campus: string | null; starts_at: string; ends_at: string; starts_on: string; ends_on: string;
  is_active: boolean; is_open: boolean; items: number;
}

export interface NetworkItem { id: number; name: string; category: string | null; occurred_on: string | null; reported_at: string | null; college: string; city: string | null }

export interface ItemTag { id: number; label: string; code: string; is_active: boolean; scan_count: number; last_scanned_at: string | null; created_at: string; url: string }

export interface MapPin { id: number; name: string; category: string | null; location: string | null; status: string; lat: number; lng: number; reported_at: string }

/** Shown to a claimant on the paper-plane note: who found the item (never contact details). */
export interface Finder {
  name: string; role: string | null; department: string | null;
  found_at: string | null; found_on: string | null; reported_at: string | null;
  ref: string; pickup: string | null; college: string | null;
  /** Only filled once staff approve the claim. */
  email?: string | null; phone?: string | null;
}
