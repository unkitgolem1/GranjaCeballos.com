from locust import HttpUser, task, between


class UserBehavior(HttpUser):
    wait_time = between(0.5, 2.0)

    @task(10)
    def view_welcome(self):
        self.client.get("/partial/welcome", name="[10] welcome")

    @task(5)
    def view_logistic(self):
        self.client.get("/logistic", name="[5] logistic")

    @task(3)
    def checkout_get(self):
        self.client.get(
            "/checkout?paquete_id=a0000000-0000-0000-0000-000000000003",
            name="[3] checkout GET",
        )

    @task(1)
    def pdf(self):
        with self.client.get(
            "/api/ticket/a0000000-0000-0000-0000-000000000003.pdf",
            name="[1] PDF ticket",
            catch_response=True,
        ) as r:
            if r.status_code == 404:
                r.success()
            elif r.elapsed.total_seconds() > 10:
                r.failure(">10s timeout")
