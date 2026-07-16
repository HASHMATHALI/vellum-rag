import React, { useEffect, useRef } from 'react';

export const FluidCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const requestRef = useRef<number | null>(null);
  
  // Easing coordinates for multi-layered fluid spotlight
  const mouseRef = useRef({
    targetX: 0,
    targetY: 0,
    // Inner spotlight (faster follow)
    innerX: 0,
    innerY: 0,
    // Outer halo (slower follow, lagging behind)
    outerX: 0,
    outerY: 0
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const resizeCanvas = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();
    
    // Set initial coordinates to center
    mouseRef.current.targetX = window.innerWidth / 2;
    mouseRef.current.targetY = window.innerHeight / 2;
    mouseRef.current.innerX = window.innerWidth / 2;
    mouseRef.current.innerY = window.innerHeight / 2;
    mouseRef.current.outerX = window.innerWidth / 2;
    mouseRef.current.outerY = window.innerHeight / 2;

    const handleMouseMove = (e: MouseEvent) => {
      mouseRef.current.targetX = e.clientX;
      mouseRef.current.targetY = e.clientY;
    };
    
    window.addEventListener('mousemove', handleMouseMove);
    
    // Animation loop
    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      const mouse = mouseRef.current;
      const isDark = document.documentElement.classList.contains('dark');
      
      // Update spring/damping coordinates
      // Fast inner glow
      mouse.innerX += (mouse.targetX - mouse.innerX) * 0.12;
      mouse.innerY += (mouse.targetY - mouse.innerY) * 0.12;
      
      // Slow outer lagging halo
      mouse.outerX += (mouse.targetX - mouse.outerX) * 0.045;
      mouse.outerY += (mouse.targetY - mouse.outerY) * 0.045;
      
      // Render layered gradients
      if (isDark) {
        // 1. Slow Outer Halo (Very large, extremely soft)
        const outerGrad = ctx.createRadialGradient(
          mouse.outerX, mouse.outerY, 0,
          mouse.outerX, mouse.outerY, 450
        );
        outerGrad.addColorStop(0, 'rgba(255, 255, 255, 0.035)');
        outerGrad.addColorStop(0.5, 'rgba(255, 255, 255, 0.015)');
        outerGrad.addColorStop(1, 'rgba(255, 255, 255, 0)');
        
        ctx.beginPath();
        ctx.arc(mouse.outerX, mouse.outerY, 450, 0, Math.PI * 2);
        ctx.fillStyle = outerGrad;
        ctx.fill();
        
        // 2. Fast Inner Glow (Medium size, slightly brighter core)
        const innerGrad = ctx.createRadialGradient(
          mouse.innerX, mouse.innerY, 0,
          mouse.innerX, mouse.innerY, 180
        );
        innerGrad.addColorStop(0, 'rgba(255, 255, 255, 0.06)');
        innerGrad.addColorStop(0.6, 'rgba(255, 255, 255, 0.01)');
        innerGrad.addColorStop(1, 'rgba(255, 255, 255, 0)');
        
        ctx.beginPath();
        ctx.arc(mouse.innerX, mouse.innerY, 180, 0, Math.PI * 2);
        ctx.fillStyle = innerGrad;
        ctx.fill();
      } else {
        // Light mode: soft shadows/zinc lighting
        // 1. Slower Outer Shadow Halo
        const outerGrad = ctx.createRadialGradient(
          mouse.outerX, mouse.outerY, 0,
          mouse.outerX, mouse.outerY, 400
        );
        outerGrad.addColorStop(0, 'rgba(24, 24, 27, 0.015)');
        outerGrad.addColorStop(0.5, 'rgba(24, 24, 27, 0.005)');
        outerGrad.addColorStop(1, 'rgba(24, 24, 27, 0)');
        
        ctx.beginPath();
        ctx.arc(mouse.outerX, mouse.outerY, 400, 0, Math.PI * 2);
        ctx.fillStyle = outerGrad;
        ctx.fill();
        
        // 2. Faster Inner Light Glow
        const innerGrad = ctx.createRadialGradient(
          mouse.innerX, mouse.innerY, 0,
          mouse.innerX, mouse.innerY, 150
        );
        innerGrad.addColorStop(0, 'rgba(24, 24, 27, 0.025)');
        innerGrad.addColorStop(0.6, 'rgba(24, 24, 27, 0.005)');
        innerGrad.addColorStop(1, 'rgba(24, 24, 27, 0)');
        
        ctx.beginPath();
        ctx.arc(mouse.innerX, mouse.innerY, 150, 0, Math.PI * 2);
        ctx.fillStyle = innerGrad;
        ctx.fill();
      }
      
      requestRef.current = requestAnimationFrame(render);
    };
    
    render();
    
    return () => {
      window.removeEventListener('resize', resizeCanvas);
      window.removeEventListener('mousemove', handleMouseMove);
      if (requestRef.current) {
        cancelAnimationFrame(requestRef.current);
      }
    };
  }, []);
  
  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none z-[1] w-full h-full"
    />
  );
};
