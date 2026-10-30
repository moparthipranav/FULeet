import { useEffect, useState } from "react";
import problemService from "../services/problemService";
import type { ProblemListItem } from "../types/problem";

export default function ProblemList() {
  const [problems, setProblems] = useState<ProblemListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchProblems() {
      try {
        setLoading(true);
        setError(null);

        const response = await problemService.getAllProblems();
        setProblems(response.data);
      } catch (err) {
        console.error("Failed to fetch problems:", err);
        setError("Could not load problems. Please try again.");
      } finally {
        setLoading(false);
      }
    }

    void fetchProblems();
  }, []);

  if (loading) return <p>Loading problems...</p>;

  if (error) {
    return <p role="alert">{error}</p>;
  }

  if (problems.length === 0) {
    return <p>No problems available.</p>;
  }

  return (
    <main>
      <h1>Problems</h1>

      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Difficulty</th>
            <th>Status</th>
            <th>Favourite</th>
          </tr>
        </thead>

        <tbody>
          {problems.map((problem) => (
            <tr key={problem.problem_id}>
              <td>{problem.title}</td>
              <td>{problem.difficulty}</td>
              <td>{problem.status ?? "Not attempted"}</td>
              <td>{problem.is_favourite ? "Yes" : "No"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}