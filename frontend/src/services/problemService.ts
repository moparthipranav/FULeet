import apiService from "./apiService";
import type {
  UUID,
  ProblemListItem,
  ProblemWorkspace,
  DraftSavePayload,
  BookmarkTogglePayload,
} from "../types/problem";

export const problemService = {
  // Fetch all problems
  getAllProblems: (userId?: UUID) =>
    apiService.get<ProblemListItem[]>("/problems", {
      params: userId ? { user_id: userId } : {},
    }),

  // Fetch one problem and its workspace
  getWorkspace: (slug: string, userId?: UUID) =>
    apiService.get<ProblemWorkspace>(
      `/problems/${encodeURIComponent(slug)}`,
      {
        params: userId ? { user_id: userId } : {},
      }
    ),

  // Save the user's code draft
  saveDraft: (slug: string, payload: DraftSavePayload) =>
    apiService.put<{ status: string; language: string },
      DraftSavePayload>(
      `/problems/${encodeURIComponent(slug)}/draft`,
      payload
    ),

  // Update favourite / solve-again status
  toggleBookmark: (
    slug: string,
    payload: BookmarkTogglePayload
  ) =>
    apiService.patch<{
      problem_id: UUID;
      is_favourite: boolean;
      solve_again: boolean;
    }, BookmarkTogglePayload>(
      `/problems/${encodeURIComponent(slug)}/bookmark`,
      payload
    ),
};

export default problemService;
