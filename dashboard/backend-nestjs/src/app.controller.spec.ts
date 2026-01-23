import { Test, TestingModule } from "@nestjs/testing";
import { AppController } from "./app.controller";

describe("AppController", () => {
  let controller: AppController;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [AppController],
    }).compile();

    controller = module.get<AppController>(AppController);
  });

  describe("getRoot", () => {
    it("should return API info", () => {
      const result = controller.getRoot();

      expect(result).toEqual({
        name: "Conductor Dashboard API",
        version: "1.0.0",
        docs: "/docs",
      });
    });
  });

  describe("healthCheck", () => {
    it("should return healthy status", () => {
      const result = controller.healthCheck();

      expect(result.status).toBe("healthy");
      expect(result.timestamp).toBeDefined();
    });

    it("should return valid ISO timestamp", () => {
      const before = new Date().toISOString();
      const result = controller.healthCheck();
      const after = new Date().toISOString();

      expect(result.timestamp >= before).toBe(true);
      expect(result.timestamp <= after).toBe(true);
    });
  });
});
