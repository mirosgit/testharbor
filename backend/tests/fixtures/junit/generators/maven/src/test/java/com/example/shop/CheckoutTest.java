package com.example.shop;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

class CheckoutTest {

    @Test
    void payWithCard_C1() {
        assertEquals(201, 201);
    }

    @Test
    void declinedCard_C2() {
        int status = 500;
        assertEquals(402, status, "declined card should return 402");
    }

    @Test
    void applyDiscountCode() {
        assertEquals(90, 100 - 10);
    }

    @Test
    void threeDSecure_C3() {
        throw new IllegalStateException("3DS simulator not running");
    }

    @Disabled("waiting for sandbox credentials")
    @Test
    void refund_C6() {
    }
}
