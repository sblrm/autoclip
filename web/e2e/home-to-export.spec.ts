import { expect, test } from "@playwright/test";

test("new user imports, selects subject, approves, and exports", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Mulai proyek" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "source.mp4",
    mimeType: "video/mp4",
    buffer: Buffer.from("fixture"),
  });
  await page.waitForURL(/\/projects\//);

  await page.getByRole("button", { name: "Analisis klip" }).click();
  await expect(page.getByRole("button", { name: "Deteksi wajah" })).toBeVisible();
  await page.getByRole("button", { name: "Deteksi wajah" }).click();
  await expect(page.getByRole("button", { name: "Subject 1" })).toBeVisible();
  await page.getByRole("button", { name: "Subject 1" }).click();
  await page.getByRole("button", { name: "Buat pratinjau" }).click();
  await expect(page.getByRole("button", { name: "Setujui pratinjau" })).toBeEnabled();
  await page.getByRole("button", { name: "Setujui pratinjau" }).click();
  await expect(page.getByRole("button", { name: "Ekspor 9:16" })).toBeEnabled();
  await page.getByRole("button", { name: "Ekspor 9:16" }).click();
  await expect(page.getByRole("link", { name: /MP4 export libx264 yunet_cpu/ })).toBeVisible();
});

test("GPU settings explain and expose fixed setup components", async ({ page }) => {
  await page.goto("/settings");

  await expect(page.getByRole("heading", { name: "Setup GPU tracking" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Pasang PyTorch CUDA 12.8" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Pasang ONNX Runtime CUDA 12.8" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unduh YuNet 2023mar" })).toBeVisible();
  await expect(page.getByText(/NVENC belum siap/)).toBeVisible();
  await page.getByRole("button", { name: "Kembali ke Home" }).click();
  await expect(page.getByRole("button", { name: "Mulai proyek" })).toBeVisible();
});
