import { readRoute } from "./routes";

test("restores Home, Settings, and project routes after browser navigation", () => {
  expect(readRoute(new URL("http://local.test/"))).toEqual({ kind: "home" });
  expect(readRoute(new URL("http://local.test/projects/p-1"))).toEqual({ kind: "project", projectId: "p-1" });
  expect(readRoute(new URL("http://local.test/settings"))).toEqual({ kind: "settings" });
});
