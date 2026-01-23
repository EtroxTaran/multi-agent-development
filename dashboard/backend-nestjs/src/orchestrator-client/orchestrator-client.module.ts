import { Module, Global } from "@nestjs/common";
import { ConfigModule } from "@nestjs/config";
import { OrchestratorClientService } from "./orchestrator-client.service";

@Global()
@Module({
  imports: [ConfigModule],
  providers: [OrchestratorClientService],
  exports: [OrchestratorClientService],
})
export class OrchestratorClientModule {}
