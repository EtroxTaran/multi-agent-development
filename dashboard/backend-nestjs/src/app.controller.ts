import { Controller, Get } from "@nestjs/common";
import { ApiOperation, ApiResponse, ApiTags } from "@nestjs/swagger";

@Controller()
@ApiTags("system")
export class AppController {
  @Get()
  @ApiOperation({ summary: "API root endpoint" })
  @ApiResponse({ status: 200, description: "API info" })
  getRoot() {
    return {
      name: "Conductor Dashboard API",
      version: "1.0.0",
      docs: "/docs",
    };
  }

  @Get("health")
  @ApiOperation({ summary: "Health check endpoint" })
  @ApiResponse({ status: 200, description: "Health status" })
  healthCheck() {
    return {
      status: "healthy",
      timestamp: new Date().toISOString(),
    };
  }
}
