import { Module } from '@nestjs/common';
import { WebsocketGateway } from './websocket.gateway';
import { WebsocketService } from './websocket.service';
import { OrchestratorBridgeService } from './orchestrator-bridge.service';

@Module({
  providers: [WebsocketGateway, WebsocketService, OrchestratorBridgeService],
  exports: [WebsocketService, OrchestratorBridgeService],
})
export class WebsocketModule {}