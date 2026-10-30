
export type UUID = string;

export type Difficulty = "EASY" | "MEDIUM" | "HARD";

export type ProblemStatus = "ATTEMPTED" | "SOLVED";

export type Verdict =
  | "PENDING"
  | "AC"
  | "WA"
  | "TLE"
  | "MLE"
  | "RE"
  | "CE";

// User
export interface User {
  user_id: UUID;
  username: string;
  email: string;
  gender: string | null;
  about: string | null;
  created_at: string;
}

export interface DemoUserResponse {
  user_id: UUID;
  username: string;
}

// Problems
export interface ProblemListItem {
  problem_id: UUID;
  slug: string;
  title: string;
  difficulty: Difficulty;
  status: ProblemStatus | null;
  is_favourite: boolean;
  solve_again: boolean;
}

export interface ProblemExample {
  [key: string]: unknown;
}

export interface LanguageTemplate {
  template_language: string;
  boilerplate: string;
}

export interface LanguageTemplateCreate extends LanguageTemplate {
  driver_harness: string;
}

export interface TestCase {
  expected_input: string;
  expected_output: string;
  is_sample: boolean;
  ordinal_order: number;
}

export interface SampleTestCase {
  test_case_id: UUID;
  expected_input: string;
  expected_output: string;
  ordinal_order: number;
}

export interface ProblemWorkspace {
  problem_id: UUID;
  slug: string;
  title: string;
  difficulty: Difficulty;
  prob_description: string;
  prob_image_url: string | null;
  prob_examples: ProblemExample[];
  prob_constraints: string;
  time_limit_ms: number;
  memory_limit_kb: number;
  language_templates: LanguageTemplate[];
  sample_test_cases: SampleTestCase[];
  saved_drafts: Record<string, string>;
}

export interface CreateProblemPayload {
  slug: string;
  title: string;
  difficulty: Difficulty;
  prob_description: string;
  prob_image_url?: string | null;
  prob_examples: ProblemExample[];
  prob_constraints: string;
  time_limit_ms?: number;
  memory_limit_kb?: number;
  language_templates: LanguageTemplateCreate[];
  test_cases: TestCase[];
}

export interface CreateProblemResponse {
  problem_id: UUID;
  slug: string;
}

// Drafts
export interface DraftSavePayload {
  user_id: UUID;
  language: string;
  code: string;
}

export interface DraftSaveResponse {
  status: string;
  language: string;
}

// Bookmarks and problem status
export interface BookmarkTogglePayload {
  user_id: UUID;
  is_favourite?: boolean;
  solve_again?: boolean;
}

export interface BookmarkResponse {
  problem_id: UUID;
  is_favourite: boolean;
  solve_again: boolean;
}

// Submissions
export interface Submission {
  sub_id: UUID;
  user_id: UUID;
  problem_id: UUID;
  language: string;
  submitted_code: string;
  result_verdict: Verdict;
  runtime_ms: number | null;
  memory_kb: number | null;
  error_output: string | null;
  created_at: string;
}
