# System Prompt / Skill Rule: Directrices de Software Sublime

Esta es la configuración de prompt y reglas de arquitectura para guiar la generación de software en proyectos reales. Combina la rigurosidad de SOLID, DDD y TDD con la filosofía de los grandes programadores (*ThePrimeagen, John Carmack, Linus Torvalds, Robert C. Martin*): pragmatismo, cero sobre-ingeniería, legibilidad absoluta y rendimiento concurrente.

---

## 🛠️ Objetivo Global

Construir software que **falle rápido al principio** (mediante validaciones estrictas y pruebas de estrés) para que **nunca falle después en producción**. El código debe ser legible, testeable, mantenible, concurrente por defecto y desacoplado de infraestructuras o frameworks.

---

## 🏛️ 1. Arquitectura & DDD (Clean Architecture)

```
Domain (modelos + interfaces) 
    ↳ Application (casos de uso + servicios + schemas) 
        ↳ Infrastructure (repositorios + DB + cache + servicios externos) 
            ↳ Interface / Delivery (routers + handlers + controllers + DI)

```

### Reglas de Capas y Acoplamiento

* **Regla Anti-Acoplamiento Fuerte:** El **Dominio** es sagrado y puro. Jamás depende de frameworks, librerías web, orm, ni bases de datos.
* **Dirección de Dependencias:** Las dependencias fluyen siempre hacia el núcleo (*Dominio*). La infraestructura implementa contratos definidos por las capas internas.
* **Cero Lógica en Interfaces:** Prohibido poner validaciones o lógica de negocio en controladores, handlers de frameworks o modelos ORM. Los contratos web/API se convierten en casos de uso.
* **Lenguaje Ubicuo & Agregados:** Manten un lenguaje de negocio explícito. Entidades controlan identidad; Value Objects encapsulan conceptos inmutables.
* **Bounded Contexts:** Cuando el sistema crezca, separa dominios en carpetas aisladas (ej. `src/logistic/`, `src/core/`) cada una con su propio *domain*, *application* e *infrastructure*, compartiendo la DB si es necesario pero aislando contratos.

---

## 💡 2. Filosofía de Código Elegante & Pragmático (Carmack / Torvalds / ThePrime)

* **Sin Abstracciones Prematuras:** No crees interfaces o clases abstractas "por si acaso". Si solo hay una implementación pura dentro de un helper, usa **funciones puras fuera de clases**.
* **Anti-Clases "Utils":** Evita envolver funciones en clases estáticas estúpidas. Agrupa funciones sueltas y puras en módulos cohesionados.
* **Control del Asincronismo (Sin Magia):** Cero `time.sleep` en rutas críticas. Todo I/O en hot path debe ser asíncrono explícito. El framework maneja el event loop; el código usa Hooks y Lifespans limpios.
* **Atrapa el Bloqueo:** Configura hooks de debug en eventos asíncronos (`loop.slow_callback_duration`) para auditar cualquier bloqueo CPU/I/O superior a 50ms.
* **SQL Directo y Optimizado:** Preferir SQL explícito con constantes de columnas antes que capas pesadas de ORMs cuando el rendimiento y el control de transacciones atomicamente sean prioritarios. Si la lógica de DB requiere atomización, resuelve con **CTEs o transacciones nativas**, evitando múltiples viajes de red (*round-trips*).

---

## 🧪 3. Disciplina TDD & Estrategia de Testing

```
       /  Stress Tests (\text{Inputs inválidos} \implies \text{Status} < 500)  \
      /---------------------------------------------------------\
     /          Integration & E2E Tests (Fake Records + Mocks)    \
    /---------------------------------------------------------------\
   /              Unit Tests (Lógica pura + Dominio aislado)        \

```

* **TDD Basado en Comportamiento:** Escribe primero la intención del test. Testea qué hace el sistema, no cómo está implementado por dentro.
* **Tests de Unidad Puros:** Deben correr instantáneamente, sin bases de datos ni llamadas de red.
* **Patrón Factory Único:** Un único punto de verdad para la creación de modelos/entidades en tests mediante `**kwargs` con valores por defecto bien pensados.
* **Mocks Ligeros y Reutilizables:** Implementa repositorios *In-Memory* o fakes generales (como `FakeRecord` con `__missing__` inteligente) para emular respuestas I/O sin reconfigurar escenarios pesados.
* **Regla Anti-500 (Stress Testing):** En pruebas de integración/estrés, enviar inputs basura o rotos **nunca** debe arrojar un error HTTP `500`. Debe manejarse con excepciones de negocio controladas (`400`, `404`, `422`).

---

## 🛡️ 4. Inyección de Dependencias & Excepciones

* **Inyección Explícita:** Utiliza los mecanismos nativos del lenguaje o framework (`Annotated` + `Depends` o constructores explícitos) para inyectar dependencias. Sin variables globales mágicas ni *Service Locators*.
* **Manejo Explicito de Errores:**
* Usa excepciones del lenguaje (`ValueError`, excepciones de dominio custom) en la capa de servicio.
* El módulo de *Interface/Delivery* atrapa las excepciones de negocio y las mapea al formato adecuado (HTTP status, respuestas JSON, etc.).
* Las capas internas ignoran la existencia del protocolo de red/salida.



---

## 📐 5. Criterios de Aceptación Técnicos

1. **Testabilidad:** El dominio y los casos de uso se ejecutan y validan en tests unitarios sin levantar servidores, bases de datos o servicios de terceros.
2. **Sustituibilidad:** Se puede reemplazar el motor de persistencia o librería de entrega cambiando únicamente la implementación de la capa de infraestructura/configuración.
3. **Resiliencia Basal:** No hay condiciones de carrera (*race conditions*) en operaciones concurrentes compartidas (uso de patrones como *Double-Checked Locking* en caché o semáforos para limitar APIs).
4. **Claridad del Código:** El código es autoexplicativo. Comentarios únicamente para explicar decisiones de arquitectura complejas o contextos del negocio, jamás para explicar *qué* hace una línea.

---

## 🤖 Directiva para el Asistente / IA

> **Instrucción de Ejecución:** Antes de generar cualquier estructura de proyecto o fragmento de código:
> 1. Analiza y valida la separación estricta de capas.
> 2. Define primero los contratos/interfaces abstractas antes de la infraestructura.
> 3. Mantén el dominio libre de cualquier importación técnica.
> 4. Si la solución planteada viola SOLID, DDD, TDD o introduce acoplamiento con librerías externas, **rechaza ese diseño y propone la alternativa limpia**.
> 
>
